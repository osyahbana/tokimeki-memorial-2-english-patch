using Tm2.Core;

namespace Tm2.Native;

public sealed class MainForm : Form
{
    private readonly ContentCatalog catalog;
    private readonly ComboBox discs = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 125 };
    private readonly TextBox filter = new() { PlaceholderText = "Filter scene ID", Width = 180 };
    private readonly ListBox scenes = new() { Dock = DockStyle.Fill, HorizontalScrollbar = true };
    private readonly TextBox inspection = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, Dock = DockStyle.Fill, Font = new Font("Consolas", 10), WordWrap = false };
    private readonly Label status = new() { Dock = DockStyle.Bottom, Height = 72, Padding = new Padding(12), AutoEllipsis = true };
    private readonly SceneCanvas canvas = new() { Dock = DockStyle.Fill };
    private ScriptMachine? machine;
    private SceneInfo? selected;
    public MainForm(ContentCatalog catalog)
    {
        this.catalog = catalog;
        Text = "Tokimeki Memorial 2 · Native engine research";
        ClientSize = new Size(1180, 760);
        MinimumSize = new Size(980, 680);
        BackColor = Color.FromArgb(239, 242, 244);
        Font = new Font("Segoe UI", 10);
        var title = new Label { Text = "TOKIMEKI MEMORIAL 2  /  NATIVE ENGINE", Dock = DockStyle.Top, Height = 58, Padding = new Padding(16), BackColor = Color.FromArgb(19, 43, 52), ForeColor = Color.White, Font = new Font("Segoe UI Semibold", 16) };
        var notice = new Label { Text = "Development milestone · Script execution and content inspection. Full gameplay, graphics, audio and event scheduling are not implemented.", Dock = DockStyle.Top, Height = 46, Padding = new Padding(16, 10, 8, 6), ForeColor = Color.FromArgb(79, 65, 31), BackColor = Color.FromArgb(255, 244, 213) };
        var split = new SplitContainer { Dock = DockStyle.Fill, Size = new Size(1180, 600), SplitterDistance = 335, FixedPanel = FixedPanel.Panel1 };
        var search = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 42, Padding = new Padding(5) };
        discs.Items.Add("All discs");
        foreach (var disc in catalog.Manifest.Discs.OrderBy(d => d.Number)) discs.Items.Add($"Disc {disc.Number}");
        discs.SelectedIndex = 0;
        search.Controls.AddRange([discs, filter]);
        split.Panel1.Controls.Add(scenes);
        split.Panel1.Controls.Add(search);
        var tabs = new TabControl { Dock = DockStyle.Fill };
        var executionTab = new TabPage("Native execution");
        executionTab.Controls.Add(canvas);
        var inspectTab = new TabPage("Source inspection — not playback");
        inspectTab.Controls.Add(inspection);
        tabs.TabPages.AddRange([executionTab, inspectTab]);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 45, Padding = new Padding(4) };
        AddButton(buttons, "Run from entry", StartScene);
        AddButton(buttons, "Continue", Continue);
        AddButton(buttons, "Save checkpoint", Save);
        AddButton(buttons, "Load checkpoint", Restore);
        split.Panel2.Controls.Add(tabs);
        split.Panel2.Controls.Add(status);
        split.Panel2.Controls.Add(buttons);
        Controls.Add(split);
        Controls.Add(notice);
        Controls.Add(title);
        discs.SelectedIndexChanged += (_, _) => RefreshScenes();
        filter.TextChanged += (_, _) => RefreshScenes();
        scenes.SelectedIndexChanged += (_, _) => SelectScene();
        RefreshScenes();
        if (scenes.Items.Count > 0) scenes.SelectedIndex = 0;
    }
    private void AddButton(FlowLayoutPanel panel, string title, Action action)
    {
        var button = new Button { Text = title, AutoSize = true, Height = 31, FlatStyle = FlatStyle.System };
        button.Click += (_, _) => Guard(action);
        panel.Controls.Add(button);
    }
    private void Guard(Action action)
    {
        try { action(); }
        catch (Exception e) when (e is IOException or InvalidDataException or ArgumentException or System.Text.Json.JsonException or FormatException or KeyNotFoundException)
        { status.Text = e.Message; }
    }
    private void RefreshScenes()
    {
        string disc = discs.SelectedItem?.ToString() ?? "All discs";
        scenes.BeginUpdate();
        scenes.Items.Clear();
        foreach (var entry in catalog.Manifest.Scenes.Where(s =>
            (disc == "All discs" || disc == $"Disc {s.Disc}") && s.SceneId.Contains(filter.Text, StringComparison.OrdinalIgnoreCase)))
            scenes.Items.Add(entry);
        scenes.EndUpdate();
    }
    private void SelectScene() => Guard(() =>
    {
        selected = scenes.SelectedItem as SceneInfo;
        machine = null;
        if (selected is null) return;
        var scene = catalog.Load(selected.ResourceId);
        inspection.Text = $"{selected.ResourceId}\r\nEntry: +0x{scene.Entry:X}; {scene.Instructions.Count} decoded instructions\r\n" +
            "Static scan: live event reachability is unresolved. Display order below is address order, not a playthrough.\r\n\r\n" +
            string.Join("\r\n", scene.Instructions.Select(op => $"{op.Offset:X4}  {op.Opcode:X2}  " +
                (op.Text is not null ? op.Text : op.Operands) + (op.Target is int target ? $"  -> {target:X4}" : "")));
        canvas.Set("READY", selected.SceneId, "Select Run from entry to execute the recovered script subset.\n\nUnknown operations stop execution. Source inspection shows extracted text and instructions separately.");
        status.Text = $"Disc {selected.Disc} resources available locally. No disc insertion is needed. Automatic story transitions are not implemented.";
    });
    private void StartScene()
    {
        if (selected is null) return;
        if (selected.SceneId.StartsWith("YG", StringComparison.Ordinal))
        {
            canvas.Set("NOT IMPLEMENTED", selected.SceneId, "This scene uses the childhood engine. Its instruction semantics have not yet been checked against the native interpreter. You can inspect its source in the next tab.");
            status.Text = "Childhood engine execution is blocked until its semantics are verified.";
            return;
        }
        machine = new(catalog.Load(selected.ResourceId), catalog.Manifest.CorpusId, selected.Sha256);
        Continue();
    }
    public void RunSelectedScene() => Guard(StartScene);
    private void Continue()
    {
        if (machine is null) return;
        var result = machine.Advance();
        canvas.Set(result.Status.ToString().ToUpperInvariant(), result.Speaker,
            string.IsNullOrEmpty(result.Text) ? result.Diagnostic : result.Text);
        status.Text = $"{machine.Scene.SceneId} · PC +0x{machine.State.Pc:X} · {result.Diagnostic}";
    }
    private void Save()
    {
        if (machine is null) return;
        using var dialog = new SaveFileDialog { Filter = "Native research checkpoint|*.checkpoint.json", FileName = "native.checkpoint.json" };
        if (dialog.ShowDialog() == DialogResult.OK) { machine.Save(dialog.FileName); status.Text = "Saved interpreter checkpoint. This is not a game memory-card save."; }
    }
    private void Restore()
    {
        using var dialog = new OpenFileDialog { Filter = "Native research checkpoint|*.checkpoint.json" };
        if (dialog.ShowDialog() != DialogResult.OK) return;
        var checkpoint = JsonData.Read<Checkpoint>(dialog.FileName);
        var info = catalog.Info(checkpoint.ResourceId);
        if (info.SceneId.StartsWith("YG", StringComparison.Ordinal)) throw new InvalidDataException("Childhood engine checkpoints are not supported.");
        var restored = new ScriptMachine(catalog.Load(info.ResourceId), catalog.Manifest.CorpusId, info.Sha256);
        restored.Restore(checkpoint);
        machine = restored;
        canvas.Set("RESTORED", info.SceneId, "Checkpoint restored. Press Continue to resume at the saved instruction.");
        status.Text = $"Restored Disc {info.Disc} scene without an insert-disc prompt.";
    }
}

public sealed class SceneCanvas : Control
{
    private string state = "READY", speaker = "", message = "";
    public SceneCanvas() { DoubleBuffered = true; BackColor = Color.FromArgb(21, 39, 49); }
    public void Set(string status, string name, string text) { state = status; speaker = name; message = text; Invalidate(); }
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        using var accent = new SolidBrush(Color.FromArgb(98, 209, 185));
        using var white = new SolidBrush(Color.FromArgb(239, 246, 247));
        using var muted = new SolidBrush(Color.FromArgb(162, 183, 195));
        using var card = new SolidBrush(Color.FromArgb(32, 54, 67));
        using var small = new Font("Segoe UI Semibold", 10);
        using var heading = new Font("Segoe UI Semibold", 19);
        using var body = new Font("Segoe UI", 17);
        g.DrawString("NATIVE SCRIPT ENGINE", small, accent, 28, 26);
        g.DrawString(state, small, muted, 28, 55);
        g.FillRectangle(card, 24, 108, Math.Max(1, Width - 48), Math.Max(1, Height - 156));
        g.DrawString(speaker, heading, white, new RectangleF(44, 127, Math.Max(1, Width - 88), 65));
        g.DrawString(message, body, white, new RectangleF(44, 204, Math.Max(1, Width - 88), Math.Max(1, Height - 275)));
        g.DrawString("Research build · Game presentation is not yet reconstructed", small, muted, 28, Height - 30);
    }
}
