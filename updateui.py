"""The update check and install windows (mixed into the App). The work is in updater.py."""
import queue
import threading
import tkinter as tk
import webbrowser

import updater
import version


class UpdateMixin:
    def _update_init(self):
        self._upd_q = queue.Queue()
        self._upd_busy = False
        self._upd_polling = False
        self._upd_manual = True
        self._upd_api = updater.API          # tests point this at a local fake
        self._upd_local = False

    def about_text(self):
        return ("Sanctuary %s\n"
                "A retro-friendly MUD client built for Duskholm and friends.\n\n"
                "Design, direction and testing: Valicene\n"
                "Code: Claude (Anthropic)\n\n"
                "https://github.com/%s" % (version.__version__, version.REPO))

    # ---- checking -----------------------------------------------------------------------
    def check_for_updates(self, manual=True):
        """Ask GitHub for the latest release (on a thread). Silent unless there is news, or manual."""
        if self._upd_busy:
            if manual:
                self.system("Already checking for updates.")
            return
        self._upd_busy, self._upd_manual = True, manual
        if manual:
            self.system("Checking for updates...")
        api, local = self._upd_api, self._upd_local

        def work():
            try:
                self._upd_q.put(("latest", updater.fetch_latest(api, local)))
            except updater.UpdateError as e:
                self._upd_q.put(("error", str(e)))
            except Exception as e:
                self._upd_q.put(("error", "Update check failed (%s)." % type(e).__name__))
        threading.Thread(target=work, daemon=True).start()
        self._upd_poll()

    def _upd_poll(self):
        """Handle whatever the worker has produced; keep looking only while work is pending."""
        while True:
            try:
                kind, payload = self._upd_q.get_nowait()
            except queue.Empty:
                break
            self._upd_handle(kind, payload)
        if self._upd_busy and not self._upd_polling:
            self._upd_polling = True
            try:
                self.root.after(200, self._upd_tick)
            except tk.TclError:
                self._upd_polling = False

    def _upd_tick(self):
        self._upd_polling = False
        self._upd_poll()

    def _upd_handle(self, kind, payload):
        if kind == "latest":
            self._upd_busy = False
            rel = payload
            if not updater.is_newer(rel["tag"]):
                if self._upd_manual:
                    self.system("You have the latest version (%s)." % version.__version__)
            elif self._upd_manual or self.cfg.get("update_skip") != rel["tag"]:
                self.show_update(rel)
        elif kind == "error":
            self._upd_busy = False
            if self._upd_manual:
                self.system(payload)
        elif kind == "progress":
            pct = payload
            self.set_notice("Downloading update... %d%%" % pct, 20)
        elif kind == "ready":
            self._upd_busy = False
            self.set_notice("", 0)
            self.confirm_restart(payload)
        elif kind == "failed":
            self._upd_busy = False
            self.set_notice("", 0)
            self.system(payload)

    # ---- telling the person --------------------------------------------------------------
    def show_update(self, rel):
        frozen = updater.running_exe() is not None
        notes = (rel["notes"].strip() or "(No release notes.)")
        head = "Version %s is available (you have %s)." % (rel["tag"].lstrip("vV"), version.__version__)
        self.system(head + (" Use Install update to get it." if frozen else " Download it from " + (rel["page"] or "GitHub") + "."))
        if self.dos:
            if self._overlay_open():
                return
            buttons = ([("Install", "install")] if frozen else [("Open page", "page")]) + [("Skip", "skip"), ("Later", "later")]

            def result(res, _v):
                self._upd_choice(res, rel)
            return self._dos_dialog("Update available", [], buttons, result, width=70,
                                    message=head + "\n\n" + notes[:700])
        top = tk.Toplevel(self.root)
        top.title("Update available")
        top.transient(self.root)
        tk.Label(top, text=head, justify="left", font=self.f_bold).pack(anchor="w", padx=12, pady=(10, 4))
        box = tk.Text(top, width=70, height=12, wrap="word", font=self.f_norm)
        box.insert("1.0", notes)
        box.configure(state="disabled")
        box.pack(padx=12, pady=4)
        bf = tk.Frame(top)
        bf.pack(pady=8)

        def pick(res):
            top.destroy()
            self._upd_choice(res, rel)
        if frozen:
            tk.Button(bf, text="Install update", command=lambda: pick("install")).pack(side="left", padx=4)
        else:
            tk.Button(bf, text="Open download page", command=lambda: pick("page")).pack(side="left", padx=4)
        tk.Button(bf, text="Skip this version", command=lambda: pick("skip")).pack(side="left", padx=4)
        tk.Button(bf, text="Later", command=lambda: pick("later")).pack(side="left", padx=4)
        top.bind("<Escape>", lambda e: pick("later"))
        self._theme_tree(top)
        top.focus_set()
        return top

    def _upd_choice(self, res, rel):
        if res == "skip":
            self.cfg["update_skip"] = rel["tag"]
            self._save_settings()
            self.system("I won't mention %s again. Check for updates still finds it." % rel["tag"])
        elif res == "page":
            if rel["page"].startswith("https://github.com/"):
                webbrowser.open(rel["page"])
        elif res == "install":
            self.install_update(rel)

    # ---- installing ----------------------------------------------------------------------
    def install_update(self, rel):
        if updater.running_exe() is None:
            self.system("Updating in place only works for the packaged program. Use git pull in your folder.")
            return
        if self._upd_busy:
            return
        self._upd_busy = True
        self.system("Downloading the update...")
        allow_local = self._upd_local

        def progress(got, total):
            if total:
                self._upd_q.put(("progress", int(100 * got / total)))

        def work():
            try:
                path = updater.prepare(rel, allow_local=allow_local, progress=progress)
                self._upd_q.put(("ready", path))
            except updater.UpdateError as e:
                self._upd_q.put(("failed", str(e)))
            except Exception as e:
                self._upd_q.put(("failed", "The update failed (%s); nothing was changed." % type(e).__name__))
        threading.Thread(target=work, daemon=True).start()
        self._upd_poll()

    def confirm_restart(self, new_exe):
        msg = "The update is downloaded and checked. Sanctuary will close, swap itself and start again."
        self.system(msg)

        def go():
            try:
                updater.launch_swap(updater.running_exe(), new_exe)
            except OSError as e:
                self.system("Could not start the updater (%s); nothing was changed." % type(e).__name__)
                return
            self.on_quit()
        if self.dos:
            if self._overlay_open():
                return
            self._dos_dialog("Restart to update", [], [("Restart now", "go"), ("Not now", "no")],
                             lambda res, v: go() if res == "go" else self.system("Update left for later."),
                             width=64, message=msg)
            return
        from tkinter import messagebox
        if messagebox.askyesno("Restart to update", msg + "\n\nRestart now?", parent=self.root):
            go()
        else:
            self.system("Update left for later; check for updates again to install it.")

    # ---- /update ---------------------------------------------------------------------------
    def _update_command(self, cmd, arg):
        if cmd not in ("update", "updates"):
            return False
        self.check_for_updates(manual=True)
        return True
