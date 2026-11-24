using System;
using System.Diagnostics;
using System.IO;

namespace KuroLauncher
{
    class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            string appDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string pythonw = Path.Combine(userProfile, @"AppData\Local\Programs\Python\Python312\pythonw.exe");
            if (!File.Exists(pythonw))
            {
                pythonw = "pythonw";
            }
            string launcherPy = Path.Combine(appDir, "launcher.py");

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonw;
            psi.Arguments = "\"" + launcherPy + "\" start";
            psi.WorkingDirectory = appDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;

            try
            {
                Process.Start(psi);
            }
            catch
            {
                ProcessStartInfo fallback = new ProcessStartInfo();
                fallback.FileName = Path.Combine(appDir, "start_screensaver.bat");
                fallback.WorkingDirectory = appDir;
                fallback.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(fallback);
            }
        }
    }
}
