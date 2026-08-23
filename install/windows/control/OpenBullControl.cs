using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.ServiceProcess;
using System.Threading;
using System.Windows.Forms;

namespace OpenBull
{
    internal static class Palette
    {
        public static readonly Color Bg = Color.FromArgb(10, 10, 12);
        public static readonly Color Panel = Color.FromArgb(18, 18, 21);
        public static readonly Color Card = Color.FromArgb(24, 24, 28);
        public static readonly Color CardHot = Color.FromArgb(32, 32, 37);
        public static readonly Color Line = Color.FromArgb(42, 42, 48);
        public static readonly Color Text = Color.FromArgb(245, 245, 247);
        public static readonly Color Muted = Color.FromArgb(154, 154, 164);
        public static readonly Color Live = Color.FromArgb(52, 211, 153);
        public static readonly Color LiveDim = Color.FromArgb(6, 78, 59);
        public static readonly Color Stopped = Color.FromArgb(251, 113, 133);
        public static readonly Color StoppedDim = Color.FromArgb(76, 22, 31);
        public static readonly Color Warn = Color.FromArgb(251, 191, 36);
        public static readonly Color Start = Color.FromArgb(16, 185, 129);
        public static readonly Color StartHot = Color.FromArgb(5, 150, 105);
        public static readonly Color Stop = Color.FromArgb(244, 63, 94);
        public static readonly Color StopHot = Color.FromArgb(190, 18, 60);
        public static readonly Color Ghost = Color.FromArgb(38, 38, 44);
        public static readonly Color GhostHot = Color.FromArgb(52, 52, 60);
    }

    internal static class Theme
    {
        public static Font Font(float size, FontStyle style = FontStyle.Regular)
        {
            try { return new Font("Segoe UI Variable Display", size, style); }
            catch { return new Font("Segoe UI", size, style); }
        }
    }

    internal static class Draw
    {
        public static GraphicsPath Round(Rectangle r, int radius)
        {
            int d = radius * 2;
            var p = new GraphicsPath();
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        public static void FillRound(Graphics g, Color color, Rectangle r, int radius)
        {
            using (var b = new SolidBrush(color))
            using (var p = Round(r, radius))
                g.FillPath(b, p);
        }

        public static void StrokeRound(Graphics g, Color color, Rectangle r, int radius, float width = 1f)
        {
            using (var pen = new Pen(color, width))
            using (var p = Round(r, radius))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.DrawPath(pen, p);
            }
        }
    }

    internal sealed class PillButton : Control
    {
        public Color Fill = Palette.Ghost;
        public Color FillHot = Palette.GhostHot;
        public Color TextColor = Palette.Text;
        private bool _hot;
        private bool _down;

        public PillButton()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Cursor = Cursors.Hand;
            Height = 48;
            Font = Theme.Font(11f, FontStyle.Bold);
        }

        protected override void OnMouseEnter(EventArgs e) { _hot = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { _hot = false; _down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { _down = true; Invalidate(); base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { _down = false; Invalidate(); base.OnMouseUp(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            e.Graphics.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
            var c = Enabled ? (_down ? FillHot : (_hot ? FillHot : Fill)) : Palette.Ghost;
            var t = Enabled ? TextColor : Palette.Muted;
            Draw.FillRound(e.Graphics, c, ClientRectangle, 14);
            TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle, t,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
    }

    internal sealed class ServiceRow : Control
    {
        public string Title;
        public string Detail;
        public bool Running;
        public bool Missing;

        public ServiceRow()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Height = 62;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
            Draw.FillRound(g, Palette.Card, ClientRectangle, 14);
            Draw.StrokeRound(g, Palette.Line, new Rectangle(0, 0, Width - 1, Height - 1), 14);

            var led = Missing ? Palette.Warn : (Running ? Palette.Live : Palette.Stopped);
            using (var b = new SolidBrush(Color.FromArgb(40, led)))
                g.FillEllipse(b, 18, 20, 22, 22);
            using (var b = new SolidBrush(led))
                g.FillEllipse(b, 23, 25, 12, 12);

            using (var title = Theme.Font(10.5f, FontStyle.Bold))
            using (var body = Theme.Font(8.5f))
            {
                TextRenderer.DrawText(g, Title, title, new Rectangle(48, 10, Width - 140, 26), Palette.Text,
                    TextFormatFlags.EndEllipsis | TextFormatFlags.VerticalCenter);
                TextRenderer.DrawText(g, Detail, body, new Rectangle(48, 32, Width - 140, 22), Palette.Muted,
                    TextFormatFlags.EndEllipsis | TextFormatFlags.VerticalCenter);
            }

            var badge = Missing ? "Missing" : (Running ? "Live" : "Off");
            var badgeFg = Missing ? Palette.Warn : (Running ? Palette.Live : Palette.Stopped);
            var badgeBg = Missing ? Color.FromArgb(40, Palette.Warn) : (Running ? Palette.LiveDim : Palette.StoppedDim);
            var br = new Rectangle(Width - 78, 19, 60, 24);
            Draw.FillRound(g, badgeBg, br, 12);
            using (var f = Theme.Font(8f, FontStyle.Bold))
                TextRenderer.DrawText(g, badge, f, br, badgeFg,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
    }

    internal sealed class ControlForm : Form
    {
        private static readonly string[] ServiceOrder = { "postgresql-x64-16", "OpenBullRedis", "OpenBullBackend", "OpenBullCaddy" };
        private static readonly Dictionary<string, string> Labels = new Dictionary<string, string>
        {
            { "postgresql-x64-16", "Database" },
            { "OpenBullRedis", "Market cache" },
            { "OpenBullBackend", "Trading API" },
            { "OpenBullCaddy", "Website" }
        };
        private static readonly Dictionary<string, string> Details = new Dictionary<string, string>
        {
            { "postgresql-x64-16", "PostgreSQL 16  ·  local only" },
            { "OpenBullRedis", "Redis  ·  127.0.0.1:6379" },
            { "OpenBullBackend", "FastAPI  ·  127.0.0.1:8000" },
            { "OpenBullCaddy", "Public HTTP  ·  port 80" }
        };

        private readonly NotifyIcon _tray;
        private readonly System.Windows.Forms.Timer _clock;
        private readonly Dictionary<string, ServiceRow> _rows = new Dictionary<string, ServiceRow>();
        private Label _hero;
        private Label _heroSub;
        private PillButton _start;
        private PillButton _stop;
        private PillButton _restart;
        private PillButton _open;
        private Label _footer;
        private bool _busy;
        private bool _exitForReal;
        private Point _drag;

        public ControlForm()
        {
            Text = "OpenBull";
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(440, 720);
            BackColor = Palette.Bg;
            DoubleBuffered = true;
            Font = Theme.Font(10f);
            Icon = MakeIcon();
            ShowInTaskbar = true;

            BuildChrome();
            BuildBody();

            _tray = new NotifyIcon
            {
                Icon = Icon,
                Text = "OpenBull",
                Visible = true,
                ContextMenuStrip = BuildTrayMenu()
            };
            _tray.DoubleClick += (s, e) => Reveal();

            _clock = new System.Windows.Forms.Timer { Interval = 1500 };
            _clock.Tick += (s, e) => RefreshStatus();
            _clock.Start();
            RefreshStatus();

            Load += (s, e) => BeginInvoke(new Action(RefreshStatus));
            Resize += (s, e) => ApplyRoundRegion();
            ApplyRoundRegion();
        }

        private void ApplyRoundRegion()
        {
            using (var p = Draw.Round(ClientRectangle, 20))
                Region = new Region(p);
        }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ClassStyle |= 0x00020000;
                return cp;
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Draw.FillRound(e.Graphics, Palette.Bg, ClientRectangle, 20);
            using (var p = new Pen(Palette.Line))
                e.Graphics.DrawPath(p, Draw.Round(new Rectangle(0, 0, Width - 1, Height - 1), 20));
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!_exitForReal && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                Hide();
                _tray.ShowBalloonTip(1600, "OpenBull is still with you",
                    "It stays in the tray. Right-click the icon to start, stop, or quit.", ToolTipIcon.Info);
                return;
            }
            _clock.Stop();
            _tray.Visible = false;
            _tray.Dispose();
            base.OnFormClosing(e);
        }

        private void BuildChrome()
        {
            var bar = new Panel { Dock = DockStyle.Top, Height = 56, BackColor = Palette.Bg };
            bar.MouseDown += StartDrag;
            bar.MouseMove += DragMove;
            Controls.Add(bar);

            var mark = new Label
            {
                Text = "OpenBull",
                ForeColor = Palette.Text,
                Font = Theme.Font(13f, FontStyle.Bold),
                AutoSize = true,
                Left = 22,
                Top = 16,
                BackColor = Color.Transparent
            };
            mark.MouseDown += StartDrag;
            mark.MouseMove += DragMove;
            bar.Controls.Add(mark);

            var chip = new Label
            {
                Text = "Control",
                ForeColor = Palette.Muted,
                Font = Theme.Font(8.5f, FontStyle.Bold),
                AutoSize = true,
                Left = 118,
                Top = 21,
                BackColor = Color.Transparent
            };
            bar.Controls.Add(chip);

            bar.Controls.Add(ChromeBtn("–", Width - 88, (s, e) => WindowState = FormWindowState.Minimized));
            bar.Controls.Add(ChromeBtn("×", Width - 48, (s, e) => Close()));
        }

        private Label ChromeBtn(string text, int left, EventHandler click)
        {
            var b = new Label
            {
                Text = text,
                Width = 32,
                Height = 32,
                Left = left,
                Top = 12,
                TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = Palette.Muted,
                Font = Theme.Font(12f),
                Cursor = Cursors.Hand
            };
            b.MouseEnter += (s, e) => b.ForeColor = Palette.Text;
            b.MouseLeave += (s, e) => b.ForeColor = Palette.Muted;
            b.Click += click;
            return b;
        }

        private void BuildBody()
        {
            var body = new Panel { Left = 20, Top = 64, Width = 400, Height = 636, BackColor = Palette.Bg };
            Controls.Add(body);

            _hero = new Label
            {
                Left = 4, Top = 8, Width = 392, Height = 36,
                Font = Theme.Font(22f, FontStyle.Bold),
                ForeColor = Palette.Text,
                Text = "Checking…",
                BackColor = Color.Transparent
            };
            _heroSub = new Label
            {
                Left = 4, Top = 46, Width = 392, Height = 40,
                Font = Theme.Font(9.5f),
                ForeColor = Palette.Muted,
                Text = "Reading Windows services",
                BackColor = Color.Transparent
            };
            body.Controls.Add(_hero);
            body.Controls.Add(_heroSub);

            int y = 100;
            foreach (var name in ServiceOrder)
            {
                var row = new ServiceRow
                {
                    Title = Labels[name],
                    Detail = Details[name],
                    Left = 0,
                    Top = y,
                    Width = 400
                };
                body.Controls.Add(row);
                _rows[name] = row;
                y += 70;
            }

            _start = new PillButton
            {
                Text = "Start",
                Left = 0,
                Top = y + 8,
                Width = 196,
                Fill = Palette.Start,
                FillHot = Palette.StartHot,
                TextColor = Color.FromArgb(6, 20, 15)
            };
            _stop = new PillButton
            {
                Text = "Stop",
                Left = 204,
                Top = y + 8,
                Width = 196,
                Fill = Palette.Stop,
                FillHot = Palette.StopHot,
                TextColor = Color.White
            };
            _restart = new PillButton { Text = "Restart", Left = 0, Top = y + 64, Width = 196 };
            _open = new PillButton { Text = "Open dashboard", Left = 204, Top = y + 64, Width = 196 };

            _start.Click += (s, e) => RunStack("start");
            _stop.Click += (s, e) => RunStack("stop");
            _restart.Click += (s, e) => RunStack("restart");
            _open.Click += (s, e) => OpenDashboard();

            body.Controls.Add(_start);
            body.Controls.Add(_stop);
            body.Controls.Add(_restart);
            body.Controls.Add(_open);

            _footer = new Label
            {
                Left = 4,
                Top = y + 128,
                Width = 392,
                Height = 48,
                Font = Theme.Font(8.5f),
                ForeColor = Palette.Muted,
                Text = "Close hides OpenBull in the tray. Quit from the tray menu.",
                BackColor = Color.Transparent
            };
            body.Controls.Add(_footer);
        }

        private ContextMenuStrip BuildTrayMenu()
        {
            var m = new ContextMenuStrip();
            m.Items.Add("Open OpenBull", null, (s, e) => Reveal());
            m.Items.Add("Open dashboard", null, (s, e) => OpenDashboard());
            m.Items.Add(new ToolStripSeparator());
            m.Items.Add("Start", null, (s, e) => RunStack("start"));
            m.Items.Add("Stop", null, (s, e) => RunStack("stop"));
            m.Items.Add("Restart", null, (s, e) => RunStack("restart"));
            m.Items.Add(new ToolStripSeparator());
            m.Items.Add("Quit OpenBull", null, (s, e) =>
            {
                _exitForReal = true;
                Close();
            });
            return m;
        }

        private void Reveal()
        {
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
        }

        private void StartDrag(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left) _drag = e.Location;
        }

        private void DragMove(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
                Location = new Point(Location.X + e.X - _drag.X, Location.Y + e.Y - _drag.Y);
        }

        private void SetBusy(bool busy)
        {
            _busy = busy;
            _start.Enabled = !busy;
            _stop.Enabled = !busy;
            _restart.Enabled = !busy;
        }

        private void RunStack(string action)
        {
            if (_busy) return;
            SetBusy(true);
            _hero.Text = action == "stop" ? "Stopping…" : action == "restart" ? "Restarting…" : "Starting…";
            _heroSub.Text = "This takes a few seconds. Status updates live.";
            var worker = new BackgroundWorker();
            worker.DoWork += (s, e) =>
            {
                if (action == "stop" || action == "restart")
                    Apply("stop");
                if (action == "start" || action == "restart")
                    Apply("start");
                Thread.Sleep(800);
            };
            worker.RunWorkerCompleted += (s, e) =>
            {
                SetBusy(false);
                RefreshStatus();
                if (e.Error != null)
                    _heroSub.Text = "Could not change services. Run OpenBull as Administrator.";
            };
            worker.RunWorkerAsync();
        }

        private static void Apply(string action)
        {
            var names = action == "stop"
                ? new[] { "OpenBullCaddy", "OpenBullBackend", "OpenBullRedis", "postgresql-x64-16" }
                : new[] { "postgresql-x64-16", "OpenBullRedis", "OpenBullBackend", "OpenBullCaddy" };
            foreach (var name in names)
            {
                try
                {
                    using (var sc = new ServiceController(name))
                    {
                        if (action == "start" && sc.Status != ServiceControllerStatus.Running)
                        {
                            sc.Start();
                            sc.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(20));
                        }
                        else if (action == "stop" && sc.Status != ServiceControllerStatus.Stopped)
                        {
                            sc.Stop();
                            sc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(20));
                        }
                    }
                }
                catch
                {
                }
                Thread.Sleep(250);
            }
        }

        private void RefreshStatus()
        {
            int live = 0, known = 0;
            foreach (var name in ServiceOrder)
            {
                var row = _rows[name];
                try
                {
                    using (var sc = new ServiceController(name))
                    {
                        known++;
                        row.Missing = false;
                        row.Running = sc.Status == ServiceControllerStatus.Running;
                        if (row.Running) live++;
                    }
                }
                catch
                {
                    row.Missing = true;
                    row.Running = false;
                }
                row.Invalidate();
            }

            if (live == known && known > 0)
            {
                _hero.Text = "Live";
                _hero.ForeColor = Palette.Live;
                _heroSub.Text = "The full stack is running. Traders can open the dashboard.";
                _tray.Text = "OpenBull  ·  Live";
            }
            else if (live == 0)
            {
                _hero.Text = "Stopped";
                _hero.ForeColor = Palette.Stopped;
                _heroSub.Text = "Nothing is serving. Press Start when you want the desk open.";
                _tray.Text = "OpenBull  ·  Stopped";
            }
            else
            {
                _hero.Text = "Partial";
                _hero.ForeColor = Palette.Warn;
                _heroSub.Text = live + " of " + known + " services are up. Restart to settle the stack.";
                _tray.Text = "OpenBull  ·  Partial";
            }
            _footer.Text = DashboardUrl() + Environment.NewLine + "Close hides the window. Quit from the tray.";
        }

        private static string DashboardUrl()
        {
            try
            {
                var env = @"C:\openbull\.env";
                if (File.Exists(env))
                {
                    foreach (var line in File.ReadAllLines(env))
                    {
                        var t = line.Trim();
                        if (t.StartsWith("FRONTEND_URL", StringComparison.OrdinalIgnoreCase))
                        {
                            var v = t.Substring(t.IndexOf('=') + 1).Trim().Trim('"');
                            if (!string.IsNullOrWhiteSpace(v)) return v.TrimEnd('/') + "/";
                        }
                    }
                }
            }
            catch { }
            return "http://127.0.0.1/";
        }

        private void OpenDashboard()
        {
            try { Process.Start(DashboardUrl()); }
            catch { }
        }

        internal static Icon MakeIcon()
        {
            using (var bmp = new Bitmap(64, 64))
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (var b = new SolidBrush(Color.FromArgb(16, 16, 18)))
                    g.FillEllipse(b, 2, 2, 60, 60);
                using (var b = new SolidBrush(Palette.Start))
                    g.FillEllipse(b, 10, 10, 44, 44);
                using (var f = new Font("Segoe UI", 16f, FontStyle.Bold))
                using (var br = new SolidBrush(Color.FromArgb(6, 20, 15)))
                {
                    var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                    g.DrawString("OB", f, br, new RectangleF(0, 2, 64, 64), sf);
                }
                return Icon.FromHandle(bmp.GetHicon());
            }
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            bool created;
            using (new Mutex(true, "OpenBullControlSingleton", out created))
            {
                if (!created) return;
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new ControlForm());
            }
        }
    }
}
