using System.Security.Cryptography;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace Tm2.Core;

public static class JsonData
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        MaxDepth = 80
    };
    public static T Read<T>(string path) => JsonSerializer.Deserialize<T>(File.ReadAllBytes(path), Options)
        ?? throw new InvalidDataException($"Empty document: {Path.GetFileName(path)}");
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    public static string CorpusHash(JsonElement document)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer, new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }))
            WriteCanonical(writer, document, true);
        return Hash(buffer.ToArray());
    }
    private static void WriteCanonical(Utf8JsonWriter writer, JsonElement element, bool root = false)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                var properties = element.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal).ToArray();
                if (properties.Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() != properties.Length)
                    throw new InvalidDataException("Duplicate JSON property.");
                foreach (var property in properties)
                {
                    if (root && property.Name == "corpusId") continue;
                    writer.WritePropertyName(property.Name);
                    WriteCanonical(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in element.EnumerateArray()) WriteCanonical(writer, item);
                writer.WriteEndArray();
                break;
            case JsonValueKind.String: writer.WriteStringValue(element.GetString()); break;
            case JsonValueKind.Number: writer.WriteNumberValue(element.GetInt64()); break;
            case JsonValueKind.True: writer.WriteBooleanValue(true); break;
            case JsonValueKind.False: writer.WriteBooleanValue(false); break;
            case JsonValueKind.Null: writer.WriteNullValue(); break;
            default: throw new InvalidDataException("Unsupported manifest value.");
        }
    }
}

public sealed class Manifest
{
    public int FormatVersion { get; set; }
    public string CorpusId { get; set; } = "";
    public List<DiscInfo> Discs { get; set; } = [];
    public List<SceneInfo> Scenes { get; set; } = [];
}
public sealed class DiscInfo
{
    public int Number { get; set; }
    public string Sha256 { get; set; } = "";
    public string Revision { get; set; } = "";
    public string Serial { get; set; } = "";
}
public sealed class SceneInfo
{
    public string ResourceId { get; set; } = "";
    public int Disc { get; set; }
    public string Key { get; set; } = "";
    public string SceneId { get; set; } = "";
    public string Path { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public int Entry { get; set; }
    public int InstructionCount { get; set; }
    public int LineCount { get; set; }
    public long SourceOffset { get; set; }
    public override string ToString() => $"Disc {Disc} · {SceneId} · {Key} @{SourceOffset:x}";
}
public sealed class Scene
{
    public int FormatVersion { get; set; }
    public string ResourceId { get; set; } = "";
    public int Disc { get; set; }
    public string Key { get; set; } = "";
    public string SceneId { get; set; } = "";
    public long SourceOffset { get; set; }
    public int Entry { get; set; }
    public int ByteLength { get; set; }
    public List<Instruction> Instructions { get; set; } = [];
    public Dictionary<int, Instruction> Validate()
    {
        if (FormatVersion != 1 || ByteLength <= 0 || Instructions is null || Instructions.Count == 0)
            throw new InvalidDataException("Unsupported or empty scene document.");
        var result = new Dictionary<int, Instruction>();
        foreach (var op in Instructions)
        {
            if (op.Opcode is < 0 or > 255 || op.Offset < 0 || op.Next <= op.Offset || op.Next > ByteLength ||
                op.Bytes.Length != op.Next - op.Offset - 1 || !result.TryAdd(op.Offset, op))
                throw new InvalidDataException("Invalid instruction range, operands or duplicate offset.");
        }
        if (!result.ContainsKey(Entry)) throw new InvalidDataException("Entry is not an instruction.");
        int priorEnd = -1;
        foreach (var op in result.Values.OrderBy(x => x.Offset))
        {
            if (op.Offset < priorEnd) throw new InvalidDataException("Overlapping instructions.");
            priorEnd = op.Next;
            if (op.Opcode is 0x30 or 0x31)
            {
                var b = op.Bytes;
                if (b.Length < 2) throw new InvalidDataException("Truncated branch.");
                int expected = op.Next + (short)(b[^2] | (b[^1] << 8));
                if (op.Target != expected || !result.ContainsKey(expected))
                    throw new InvalidDataException("Branch target is not a decoded instruction.");
            }
            if (op.Opcode is not (0x31 or 0xff) && !result.ContainsKey(op.Next))
                throw new InvalidDataException("Fallthrough is not a decoded instruction.");
        }
        return result;
    }
}
public sealed class Instruction
{
    public int Offset { get; set; }
    public int Opcode { get; set; }
    public int Next { get; set; }
    public string Operands { get; set; } = "";
    public string? Text { get; set; }
    public string? OriginalText { get; set; }
    public int? Target { get; set; }
    public byte[] Bytes => Convert.FromHexString(Operands);
}

// A disc number is part of every identity. There is no "current inserted disc".
public sealed class ContentCatalog
{
    public Manifest Manifest { get; }
    public string Root { get; }
    private readonly Dictionary<string, SceneInfo> entries;
    public ContentCatalog(string manifestPath)
    {
        Root = Path.GetDirectoryName(Path.GetFullPath(manifestPath))!;
        var document = JsonData.Read<JsonElement>(manifestPath);
        Manifest = document.Deserialize<Manifest>(JsonData.Options) ?? throw new InvalidDataException("Empty manifest.");
        if (Manifest.FormatVersion != 1 || Manifest.Discs is null || Manifest.Scenes is null || Manifest.Discs.Count == 0 || Manifest.Scenes.Count == 0 ||
            !IsHash(Manifest.CorpusId)) throw new InvalidDataException("Invalid content manifest.");
        if (JsonData.CorpusHash(document) != Manifest.CorpusId) throw new InvalidDataException("Manifest corpus hash mismatch.");
        var discs = new HashSet<int>();
        foreach (var d in Manifest.Discs)
            if (d.Number is < 1 or > 5 || !discs.Add(d.Number) || !IsHash(d.Sha256))
                throw new InvalidDataException("Invalid or duplicate disc identity.");
        entries = new(StringComparer.Ordinal);
        foreach (var entry in Manifest.Scenes)
        {
            if (!discs.Contains(entry.Disc) || !entry.ResourceId.StartsWith($"disc{entry.Disc}/", StringComparison.Ordinal)
                || !IsHash(entry.Sha256) || !entries.TryAdd(entry.ResourceId, entry))
                throw new InvalidDataException("Invalid or duplicate scene identity.");
            ResolvePath(entry.Path);
        }
    }
    private static bool IsHash(string? text) => text is not null && text.Length == 64 && text.All(Uri.IsHexDigit);
    private string ResolvePath(string relative, bool inspectLinks = false)
    {
        if (string.IsNullOrEmpty(relative) || Path.IsPathRooted(relative) || relative.Contains(':'))
            throw new InvalidDataException("Resource paths must be relative.");
        string path = Path.GetFullPath(Path.Combine(Root, relative));
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (!path.StartsWith(Root + Path.DirectorySeparatorChar, comparison))
            throw new InvalidDataException("Resource path escapes content root.");
        for (string? current = inspectLinks ? path : null; current is not null && current != Root; current = Path.GetDirectoryName(current))
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Resource paths cannot traverse symbolic links or junctions.");
        return path;
    }
    public SceneInfo Info(string id) => entries.TryGetValue(id, out var info) ? info
        : throw new KeyNotFoundException($"Scene is not in this content set: {id}");
    public Scene Load(string id)
    {
        var info = Info(id);
        byte[] bytes = File.ReadAllBytes(ResolvePath(info.Path, inspectLinks: true));
        if (JsonData.Hash(bytes) != info.Sha256) throw new InvalidDataException("Scene content hash mismatch.");
        var scene = JsonSerializer.Deserialize<Scene>(bytes, JsonData.Options)
            ?? throw new InvalidDataException("Empty scene.");
        if (scene.ResourceId != id || scene.Disc != info.Disc || scene.Key != info.Key || scene.SceneId != info.SceneId || scene.Entry != info.Entry ||
            scene.SourceOffset != info.SourceOffset || scene.Instructions is null || scene.Instructions.Count != info.InstructionCount ||
            scene.Instructions.Count(op => op.Opcode is 0x10 or 0x11) != info.LineCount)
            throw new InvalidDataException("Scene identity does not match manifest.");
        scene.Validate();
        return scene;
    }
}
