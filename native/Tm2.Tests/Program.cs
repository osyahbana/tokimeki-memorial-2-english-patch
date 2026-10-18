using System.Text.Json;
using Tm2.Core;

internal static class Program
{
    private static int passed;
    private const string Hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private static void Check(bool condition, string message)
    { if (!condition) throw new Exception(message); }
    private static void Reject<T>(Action action) where T : Exception
    {
        try { action(); } catch (T) { return; }
        throw new Exception($"Expected {typeof(T).Name}");
    }
    private static void Test(string name, Action action) { action(); passed++; Console.WriteLine($"PASS {name}"); }
    private static Scene MakeScene(params Instruction[] ops) => new()
    {
        FormatVersion = 1, Disc = 2, ResourceId = "disc2/test@0", Key = "test", SceneId = "TEST",
        ByteLength = ops.Max(x => x.Next), Entry = ops[0].Offset, Instructions = ops.ToList()
    };
    private static Instruction Op(int at, int op, string bytes = "", string? text = null, int? target = null) =>
        new() { Offset = at, Opcode = op, Operands = bytes, Next = at + 1 + bytes.Length / 2, Text = text, Target = target };
    private static ScriptMachine Machine(Scene scene) => new(scene, Hash, Hash);
    private static void WriteManifest(string path, Manifest manifest)
    {
        manifest.CorpusId = JsonData.CorpusHash(JsonSerializer.SerializeToElement(manifest, JsonData.Options));
        File.WriteAllText(path, JsonSerializer.Serialize(manifest, JsonData.Options));
    }
    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 2 && args[0] == "--audit") return Audit(args[1]);
            Test("383 actual-machine expression oracle vectors", () =>
            {
                var root = JsonData.Read<JsonElement>(Path.Combine(AppContext.BaseDirectory, "vm-vectors.json"));
                int count = 0;
                foreach (var vector in root.GetProperty("vectors").EnumerateArray())
                {
                    string name = vector.GetProperty("name").GetString()!;
                    byte[] bytes = Convert.FromHexString(vector.GetProperty("expressionHex").GetString()!);
                    var initial = vector.GetProperty("initialVariables").EnumerateArray().Select(x => x.GetInt32()).ToArray();
                    int result = Expression.Decode(bytes).Evaluate(initial);
                    Check(result == vector.GetProperty("expectedValue").GetInt32(), name + " result");
                    Check(initial.SequenceEqual(vector.GetProperty("finalVariables").EnumerateArray().Select(x => x.GetInt32())), name + " side effects");
                    Check(bytes.Length == vector.GetProperty("expectedBytesConsumed").GetInt32(), name + " consumed length");
                    count++;
                }
                Check(count == 383, "Missing vectors");
            });
            Test("unsupported queries and malformed expressions fail", () =>
            {
                Reject<UnsupportedOperation>(() => Expression.Decode([0x50, 1]));
                Reject<UnsupportedOperation>(() => Expression.Decode([0x4f, 0x10]));
                Reject<UnsupportedOperation>(() => Expression.Decode([0x4d, 0x14]));
                Reject<InvalidDataException>(() => Expression.Decode([0x4e, 1]));
                Reject<InvalidDataException>(() => Expression.Decode([0x4e, 1, 0, 0]));
                Reject<UnsupportedOperation>(() => Expression.Decode([0x44, 0x4e, 1, 0, 0x4e, 0, 0]).Evaluate(new int[16]));
            });
            Test("actual-machine F0 reset and supported host completion vectors", () =>
            {
                var root = JsonData.Read<JsonElement>(Path.Combine(AppContext.BaseDirectory, "lifecycle-vectors.json"));
                foreach (var vector in root.GetProperty("resetVectors").EnumerateArray())
                {
                    var machine = Machine(MakeScene(Op(0, 0xf0), Op(1, 0xff)));
                    machine.State.Variables = vector.GetProperty("initialVariables").EnumerateArray().Select(x => x.GetInt32()).ToArray();
                    foreach (var field in vector.GetProperty("resetFields").EnumerateArray())
                        machine.State.EngineFields[field.GetProperty("address").GetString()![2..]] = field.GetProperty("initialValue").GetInt32();
                    Check(machine.Advance().Status == RunStatus.HostEvent, "F0 event missing");
                    Check(machine.State.Variables.SequenceEqual(vector.GetProperty("finalVariables").EnumerateArray().Select(x => x.GetInt32())), "F0 oracle variables");
                    foreach (var field in vector.GetProperty("resetFields").EnumerateArray())
                        Check(machine.State.EngineFields[field.GetProperty("address").GetString()![2..]] == field.GetProperty("expectedValue").GetInt32(), "F0 oracle field");
                    var eventBytes = Convert.FromHexString(vector.GetProperty("expectedEventHex").GetString()!);
                    Check(machine.State.PendingHostEvent == (eventBytes[0] | eventBytes[1] << 8) && eventBytes.Skip(2).All(x => x == 0), "F0 event identity");
                    Check(machine.State.Pc == 1, "F0 should not rewind");
                }
                foreach (var vector in root.GetProperty("hostDirectCompletionVectors").EnumerateArray())
                {
                    byte a = vector.GetProperty("sceneContextByte3c").GetByte(), b = vector.GetProperty("sceneContextByte3d").GetByte(), tag = vector.GetProperty("currentTag").GetByte();
                    var machine = Machine(MakeScene(Op(0, 0xf0), Op(1, 0xff))); machine.Advance();
                    bool acknowledged = machine.TryCompleteInitialization(a, b, tag);
                    if (acknowledged) Check(vector.GetProperty("expectedResumeGate").GetInt32() == 1 && !vector.GetProperty("expectedExternalTransition").GetBoolean(), "Unsafe host acknowledgement");
                    Check(acknowledged == (a == tag && b % 10 == 1), "Conservative host subset changed");
                }
            });
            Test("conditional jump executes only selected line", () =>
            {
                foreach (int value in new[] { 0, 1 })
                {
                    var s = MakeScene(Op(0, 0x30, $"4e0{value}000500", target: 11), Op(6, 0x10, "00", "True"),
                        Op(8, 0x31, "0200", target: 13), Op(11, 0x10, "00", "False"), Op(13, 0x80), Op(14, 0xff));
                    var m = Machine(s);
                    var result = m.Advance();
                    Check(result.Status == RunStatus.Message && result.Text == (value == 0 ? "False" : "True"), "Wrong branch");
                    Check(m.Advance().Status == RunStatus.Ended, "No outer end event");
                    Check(m.State.Pc == 14, "End marker PC should remain on FF");
                }
            });
            Test("unknown instruction preserves PC and variables", () =>
            {
                var m = Machine(MakeScene(Op(0, 0xa7, "01"), Op(2, 0xff)));
                Check(m.Advance().Status == RunStatus.Blocked && m.State.Pc == 0 && m.State.Variables.All(x => x == 0), "Unknown instruction skipped");
            });
            Test("F0 reset emits a pending host event without guessing context", () =>
            {
                var machine = Machine(MakeScene(Op(0, 0xf0), Op(1, 0xff)));
                machine.State.Variables = Enumerable.Range(1, 16).ToArray();
                machine.State.EngineFields["8011b574"] = 100;
                Check(machine.Advance().Status == RunStatus.HostEvent, "Missing initialization event");
                Check(machine.State.Variables.Take(8).All(x => x == 0) && machine.State.Variables.Skip(8).SequenceEqual(Enumerable.Range(9, 8)), "F0 reset register scope");
                Check(machine.State.EngineFields.Count == 8 && machine.State.EngineFields.Values.All(x => x == 0), "F0 context reset");
                Check(machine.Advance().Status == RunStatus.HostEvent && machine.State.Pc == 1, "Pending event bypassed");
                Check(!machine.TryCompleteInitialization(2, 1, 3) && !machine.TryCompleteInitialization(2, 2, 2), "Unsupported host path acknowledged");
                Check(machine.TryCompleteInitialization(2, 11, 2) && machine.Advance().Status == RunStatus.Ended, "Measured direct host path failed");
            });
            Test("conditional assignment commits before branch", () =>
            {
                var scene = MakeScene(Op(0, 0x30, "4d004e00000300", target: 11), Op(8, 0x31, "0000", target: 11), Op(11, 0xff));
                var machine = Machine(scene);
                machine.State.Variables[0] = 99;
                Check(machine.Advance().Status == RunStatus.Ended && machine.State.Variables[0] == 0, "Conditional expression assignment lost");
            });
            Test("expression failure rolls back assignment side effects", () =>
            {
                var op = Op(0, 0x40, "414d004e0700444e01004e0000");
                var m = Machine(MakeScene(op, Op(op.Next, 0xff)));
                Check(m.Advance().Status == RunStatus.Blocked && m.State.Pc == 0 && m.State.Variables[0] == 0, "Partial assignment leaked");
            });
            Test("infinite loop bounded without invented continuation", () =>
            {
                var m = Machine(MakeScene(Op(0, 0x31, "fdff", target: 0)));
                Check(m.Advance(25).Status == RunStatus.Blocked && m.State.Pc == 0, "Loop escaped");
            });
            Test("reject branch into operand and overlapping ranges", () =>
            {
                Reject<InvalidDataException>(() => MakeScene(Op(0, 0x31, "feff", target: 1), Op(3, 0xff)).Validate());
                Reject<InvalidDataException>(() => MakeScene(Op(0, 0x10, "0000", "Test"), Op(1, 0xff), Op(3, 0xff)).Validate());
            });
            Test("native checkpoint resumes next message and rejects other corpus", () =>
            {
                var scene = MakeScene(Op(0, 0x10, "00", "First"), Op(2, 0x80), Op(3, 0x10, "00", "Second"), Op(5, 0x80), Op(6, 0xff));
                var original = Machine(scene);
                Check(original.Advance().Text == "First", "First message missing");
                string path = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".checkpoint.json");
                try
                {
                    original.Save(path);
                    var restored = Machine(scene);
                    restored.Restore(JsonData.Read<Checkpoint>(path));
                    Check(restored.Advance().Text == "Second", "Checkpoint repeated/skipped dialogue");
                    var wrong = JsonData.Read<Checkpoint>(path); wrong.CorpusId = new string('b', 64);
                    Reject<InvalidDataException>(() => restored.Restore(wrong));
                }
                finally { File.Delete(path); }
            });
            Test("resource routing keeps same-name scenes on five discs distinct", () =>
            {
                string root = Path.Combine(Path.GetTempPath(), "tm2-native-" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(root);
                try
                {
                    var manifest = new Manifest { FormatVersion = 1, CorpusId = Hash };
                    for (int disc = 1; disc <= 5; disc++)
                    {
                        var scene = MakeScene(Op(0, 0x10, "00", $"Disc {disc}"), Op(2, 0x80), Op(3, 0xff));
                        scene.Disc = disc; scene.ResourceId = $"disc{disc}/test@0";
                        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(scene, JsonData.Options);
                        string file = $"disc{disc}.json"; File.WriteAllBytes(Path.Combine(root, file), bytes);
                        manifest.Discs.Add(new() { Number = disc, Sha256 = Hash });
                        manifest.Scenes.Add(new() { ResourceId = scene.ResourceId, Disc = disc, Key = scene.Key, SceneId = scene.SceneId,
                            Path = file, Sha256 = JsonData.Hash(bytes), Entry = 0, InstructionCount = 3, LineCount = 1 });
                    }
                    string path = Path.Combine(root, "manifest.json");
                    WriteManifest(path, manifest);
                    var catalog = new ContentCatalog(path);
                    foreach (int disc in new[] { 1, 5, 2, 4, 3, 1 })
                        Check(Machine(catalog.Load($"disc{disc}/test@0")).Advance().Text == $"Disc {disc}", "Wrong resource routed");
                    File.AppendAllText(Path.Combine(root, "disc1.json"), " ");
                    Reject<InvalidDataException>(() => catalog.Load("disc1/test@0"));
                    manifest.Scenes[0].SceneId = "ALTERED";
                    File.WriteAllText(path, JsonSerializer.Serialize(manifest, JsonData.Options));
                    Reject<InvalidDataException>(() => new ContentCatalog(path));
                    manifest.Scenes[0].Path = "../outside.json";
                    WriteManifest(path, manifest);
                    Reject<InvalidDataException>(() => new ContentCatalog(path));
                }
                finally { Directory.Delete(root, true); }
            });
            Console.WriteLine($"PASS {passed} native test groups, including 383 machine-code oracle vectors.");
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }
    private static int Audit(string path)
    {
        var catalog = new ContentCatalog(path);
        int checkedScenes = 0, messages = 0, ended = 0, blocked = 0, childhood = 0, pendingHost = 0;
        var blockers = new Dictionary<string, int>();
        var runnable = new List<object>();
        foreach (var info in catalog.Manifest.Scenes)
        {
            var scene = catalog.Load(info.ResourceId);
            checkedScenes++;
            if (checkedScenes % 1000 == 0) Console.Error.WriteLine($"Audited {checkedScenes}/{catalog.Manifest.Scenes.Count} scene candidates");
            if (info.SceneId.StartsWith("YG", StringComparison.Ordinal)) { childhood++; continue; }
            var machine = new ScriptMachine(scene, catalog.Manifest.CorpusId, info.Sha256);
            var result = machine.Advance();
            if (result.Status == RunStatus.Message) { messages++; if (runnable.Count < 10) runnable.Add(new { info.ResourceId, result.Text }); }
            else if (result.Status == RunStatus.HostEvent) pendingHost++;
            else if (result.Status == RunStatus.Ended) ended++;
            else
            {
                blocked++;
                string reason = result.Diagnostic.Split(" at ")[0];
                blockers[reason] = blockers.GetValueOrDefault(reason) + 1;
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(new { checkedScenes, childhoodNotExecuted = childhood, firstMessageReached = messages,
            endReached = ended, unsupportedStopped = blocked, pendingHostEvents = pendingHost, blockers, runnable,
            limitations = "Zeroed research state only; scanned/stale candidates are not verified live gameplay." }, JsonData.Options));
        return 0;
    }
}
