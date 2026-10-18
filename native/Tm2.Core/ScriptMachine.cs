using System.Text.Json;
using System.Text.RegularExpressions;

namespace Tm2.Core;

public enum RunStatus { Message, HostEvent, Ended, Blocked }
public sealed record RunResult(RunStatus Status, int Offset, string Speaker, string Text, string Diagnostic);
public sealed class Checkpoint
{
    public int FormatVersion { get; set; } = 1;
    public string CorpusId { get; set; } = "";
    public string ResourceId { get; set; } = "";
    public string SceneHash { get; set; } = "";
    public int Pc { get; set; }
    public int[] Variables { get; set; } = new int[16];
    public string Speaker { get; set; } = "";
    public string PendingText { get; set; } = "";
    public bool JoinNext { get; set; }
    public bool Ended { get; set; }
    public string Name1 { get; set; } = "Player";
    public string Name2 { get; set; } = "Player";
    public string Name3 { get; set; } = "Player";
    public int? PendingHostEvent { get; set; }
    // Field names preserve the recovered source addresses until their roles are established.
    public Dictionary<string, int> EngineFields { get; set; } = new();
}
public sealed class ScriptMachine
{
    private readonly Dictionary<int, Instruction> code;
    public Scene Scene { get; }
    public Checkpoint State { get; private set; }
    public ScriptMachine(Scene scene, string corpusId, string sceneHash)
    {
        Scene = scene;
        code = scene.Validate();
        State = new() { CorpusId = corpusId, ResourceId = scene.ResourceId, SceneHash = sceneHash, Pc = scene.Entry };
    }
    public RunResult Advance(int instructionBudget = 10000)
    {
        if (State.Ended) return Result(RunStatus.Ended, "Scene path ended.");
        if (State.PendingHostEvent is not null) return InitializationEvent();
        for (int step = 0; step < instructionBudget; step++)
        {
            if (!code.TryGetValue(State.Pc, out var op)) return Result(RunStatus.Blocked, "PC is not an instruction boundary.");
            int[] candidate = (int[])State.Variables.Clone();
            try
            {
                int next = op.Next;
                switch (op.Opcode)
                {
                    case 0x00: case 0x3e: break;
                    case 0x18:
                        State.Speaker = Expand(op.Text ?? throw new InvalidDataException("Missing speaker text."));
                        break;
                    case 0x10: case 0x11:
                        string text = Expand(op.Text ?? throw new InvalidDataException("Missing line text."));
                        if (State.PendingText.Length > 0 && !State.JoinNext) State.PendingText += "\n";
                        State.PendingText += text.Replace("{nobreak}", "", StringComparison.Ordinal);
                        State.JoinNext = text.EndsWith("{nobreak}", StringComparison.Ordinal);
                        break;
                    case 0x30:
                        if (Expression.Decode(op.Bytes[..^2]).Evaluate(candidate) == 0) next = op.Target!.Value;
                        break;
                    case 0x31: next = op.Target!.Value; break;
                    case 0x40: Expression.Decode(op.Bytes).Evaluate(candidate); break;
                    case 0xf0:
                        Array.Clear(candidate, 0, 8);
                        State.Variables = candidate;
                        foreach (string field in InitializationFields) State.EngineFields[field] = 0;
                        State.Pc = next;
                        State.PendingHostEvent = 0x0c01;
                        return InitializationEvent();
                    case 0x80:
                        var message = new RunResult(RunStatus.Message, op.Offset, State.Speaker, State.PendingText, "Waiting for input.");
                        State.PendingText = ""; State.JoinNext = false; State.Pc = next;
                        return message;
                    case 0xff:
                        State.Ended = true;
                        return Result(RunStatus.Ended, "Scene path ended; event scheduling is not implemented.");
                    default:
                        throw new UnsupportedOperation($"Statement {op.Opcode:X2} at +0x{op.Offset:X} is not reconstructed. Operands: {op.Operands}");
                }
                State.Variables = candidate;
                State.Pc = next;
            }
            catch (Exception e) when (e is UnsupportedOperation or InvalidDataException or FormatException)
            { return Result(RunStatus.Blocked, e.Message); }
        }
        return Result(RunStatus.Blocked, $"Stopped after {instructionBudget} instructions without a message (possible loop).");
    }
    private RunResult Result(RunStatus status, string diagnostic) =>
        new(status, State.Pc, State.Speaker, State.PendingText, diagnostic);
    private static readonly string[] InitializationFields = ["8011b574", "80111550", "8011b5b0", "80111554", "8011b3c0", "8011b570", "8011b534", "8011b5ac"];
    private RunResult InitializationEvent() => Result(RunStatus.HostEvent,
        "F0 reset completed. Host event 01/0C is pending: original scene context/resource state is needed. Continue cannot bypass it.");
    // Only the observed direct-completion branch is implemented. Other branches
    // call unreconstructed media/resource routines and must remain pending.
    public bool TryCompleteInitialization(byte sceneContext3c, byte sceneContext3d, byte loadedResourceId)
    {
        if (State.PendingHostEvent != 0x0c01 || sceneContext3c != loadedResourceId || sceneContext3d % 10 != 1) return false;
        State.PendingHostEvent = null;
        return true;
    }
    private string Expand(string text) => Regex.Replace(text, @"\{([^}]+)\}", m => m.Groups[1].Value switch
    {
        "name1" => State.Name1, "name2" => State.Name2, "name3" => State.Name3, "nobreak" => "{nobreak}",
        _ => throw new UnsupportedOperation($"Dynamic text field {m.Value} requires game state not yet reconstructed.")
    });
    public void Save(string path)
    {
        string full = Path.GetFullPath(path);
        string temp = full + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(State, JsonData.Options));
            File.Move(temp, full, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    public void Restore(Checkpoint saved)
    {
        if (saved.FormatVersion != 1 || saved.CorpusId != State.CorpusId || saved.ResourceId != State.ResourceId ||
            saved.SceneHash != State.SceneHash || saved.Variables is null || saved.Variables.Length != 16 || !code.ContainsKey(saved.Pc) ||
            saved.Speaker is null || saved.PendingText is null || saved.Name1 is null || saved.Name2 is null || saved.Name3 is null ||
            saved.EngineFields is null || saved.PendingHostEvent is not (null or 0x0c01))
            throw new InvalidDataException("Checkpoint does not match this content/scene or has an invalid PC.");
        State = JsonSerializer.Deserialize<Checkpoint>(JsonSerializer.Serialize(saved, JsonData.Options), JsonData.Options)!;
    }
}
