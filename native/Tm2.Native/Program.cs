using Tm2.Core;

namespace Tm2.Native;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        string? Value(string flag) { int i = Array.IndexOf(args, flag); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
        string manifest = Value("--manifest") ?? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "data", "manifest.json"));
        string? render = Value("--render");
        try
        {
            if (!File.Exists(manifest))
            {
                if (render is not null) throw new FileNotFoundException("Import content before rendering.");
                using var pick = new OpenFileDialog { Title = "Choose the imported manifest.json", Filter = "Imported game manifest|manifest.json" };
                if (pick.ShowDialog() != DialogResult.OK) return 0;
                manifest = pick.FileName;
            }
            using var form = new MainForm(new ContentCatalog(manifest));
            if (render is not null)
            {
                // Render our own controls for a build artifact; no desktop capture or emulator.
                form.ShowInTaskbar = false;
                form.Show();
                Application.DoEvents();
                if (args.Contains("--run", StringComparer.Ordinal)) form.RunSelectedScene();
                Application.DoEvents();
                using var bitmap = new Bitmap(form.Width, form.Height);
                form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height));
                bitmap.Save(render, System.Drawing.Imaging.ImageFormat.Png);
                form.Close();
            }
            else Application.Run(form);
            return 0;
        }
        catch (Exception error)
        {
            if (render is null) MessageBox.Show(error.Message, "Native engine could not open content", MessageBoxButtons.OK, MessageBoxIcon.Error);
            else File.WriteAllText(render + ".error.txt", error.ToString());
            return 1;
        }
    }
}
