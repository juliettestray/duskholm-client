"""Import triggers and aliases from another client's file: File > Import from another client... and /import <file>.

The file is read first and what it holds is told in the output (what can come across, what cannot and why, what is
approximate). Only then are you asked: which world the rules belong to, whether to save the file's world too, and
whether to trust it (rules that send commands, and all aliases, arrive switched off unless you do). Nothing in the file
is ever run."""
import os
import tkinter as tk

import clientimport
from mushimport import ImportProblem

READ_MAX = 5_000_000


class ImportMixin:
    def _import_command(self, cmd, arg):
        """/import [file]"""
        if cmd != "import":
            return False
        path = (arg or "").strip().strip('"')
        if path:
            self.import_client_file(path)
        else:
            self.open_import_client()
        return True

    def open_import_client(self):
        if self.dos:
            def result(res, vals):
                if res == "read" and not self.import_client_file(vals.get("path", "")):
                    self._reopen(self.open_import_client)
            return self._dos_dialog(
                "Import from another client", [{"key": "path", "label": "File", "type": "text", "value": "", "width": 52}],
                [("Read", "read"), ("Cancel", "cancel")], result, width=72,
                message="A MUSHclient world, plugin or trigger file (.MCL, .xml). Nothing in it is run.")
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self.root, initialdir=os.path.expanduser("~"), title="Import from another client",
            filetypes=[("MUSHclient files", "*.mcl *.MCL *.xml"), ("All files", "*.*")])
        if path:
            self.import_client_file(path)

    def import_client_file(self, path):
        """Read a file, say what is in it, and ask what to do. True when there is something to import."""
        path = os.path.expanduser(str(path or "").strip().strip('"'))
        try:
            if os.path.getsize(path) > READ_MAX:
                self.system("That file is too big to be a trigger or world file (over %d MB)." % (READ_MAX // 1_000_000))
                return False
            with open(path, "rb") as f:
                data = f.read(READ_MAX + 1)
        except OSError as e:
            self.system("Could not read that file: %s" % (getattr(e, "strerror", None) or type(e).__name__))
            return False
        if data.lstrip(b"\xef\xbb\xbf \r\n\t")[:1] == b"{":                # one of our own world files (.snc)
            ok, lines = self.import_world_file(path)
            for line in lines:
                self.system(line)
            return ok
        try:
            kind, result = clientimport.read(data)
        except ImportProblem as e:
            self.system(str(e))
            return False
        for line in clientimport.report(kind, result, limit=12):
            self.system(line)
        if not (result["triggers"] or result["aliases"] or result["world"]):
            self.system("There is nothing in that file that I can import.")
            return False
        self._import_confirm(kind, result, os.path.basename(path))
        return True

    # ---- the question ----------------------------------------------------------------------------------
    def _import_defaults(self, result):
        w = result.get("world") or {}
        name = w.get("name") or self._world_name(self._shown)
        can_add = bool(w.get("host") and w.get("port")) and w.get("name", "").lower() not in {
            x["name"].lower() for x in self.cfg.get("worlds", [])}
        return name, can_add, w

    def _import_confirm(self, kind, result, filename):
        name, can_add, w = self._import_defaults(result)
        nt, na = len(result["triggers"]), len(result["aliases"])
        what = "%d trigger%s and %d alias%s" % (nt, "" if nt == 1 else "s", na, "" if na == 1 else "es")
        add_label = "Also save the world '%s' (%s:%s)" % (w.get("name", ""), w.get("host", ""), w.get("port", ""))
        trust = "I trust this file: switch on the ones that send commands, and the aliases"
        if self.dos:
            fields = [{"key": "world", "label": "Tie to world", "type": "text", "value": name, "width": 30}]
            if can_add:
                fields.append({"key": "addworld", "label": add_label[:50], "type": "check", "value": True})
            fields.append({"key": "trust", "label": "I trust it: switch them all on", "type": "check", "value": False})

            def result_cb(res, vals):
                if res == "import":
                    self._import_apply(kind, result, str(vals.get("world", "")).strip(), bool(vals.get("addworld")),
                                       bool(vals.get("trust")))
            return self._dos_dialog("Import %s" % what, fields, [("Import", "import"), ("Cancel", "cancel")], result_cb,
                                    width=66, message="Empty world name: every world. Off by default: rules that send, aliases.")
        top = tk.Toplevel(self.root)
        self._import_win = top
        top.title("Import from another client")
        top.transient(self.root)
        tk.Label(top, justify="left", anchor="w",
                 text="%s: %s can be imported (the details are in the output window)." % (filename, what)).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")
        tk.Label(top, text="Tie them to the world").grid(row=1, column=0, padx=10, sticky="w")
        wv = tk.StringVar(value=name)
        tk.Entry(top, textvariable=wv, width=30).grid(row=1, column=1, padx=10, pady=2, sticky="w")
        tk.Label(top, text="(leave it empty to use them in every world)", anchor="w").grid(
            row=2, column=1, padx=10, sticky="w")
        av = tk.BooleanVar(value=True)
        if can_add:
            tk.Checkbutton(top, text=add_label, variable=av).grid(row=3, column=0, columnspan=2, padx=10, pady=(8, 0), sticky="w")
        tv = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text=trust, variable=tv).grid(row=4, column=0, columnspan=2, padx=10, sticky="w")
        tk.Label(top, anchor="w", justify="left",
                 text="Otherwise rules that send commands and all aliases arrive switched off, for you to look over.").grid(
            row=5, column=0, columnspan=2, padx=10, sticky="w")

        def go():
            self._import_win = None
            top.destroy()
            self._import_apply(kind, result, wv.get().strip(), bool(av.get()) and can_add, bool(tv.get()))

        def cancel():
            self._import_win = None
            top.destroy()
        bf = tk.Frame(top)
        bf.grid(row=6, column=0, columnspan=2, pady=10)
        tk.Button(bf, text="Import", width=10, command=go).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=10, command=cancel).pack(side="left", padx=4)
        top.bind("<Return>", lambda e: go())
        top.bind("<Escape>", lambda e: cancel())
        top.protocol("WM_DELETE_WINDOW", cancel)
        self._theme_tree(top)
        return top

    def _import_apply(self, kind, result, world_name, add_world, trust):
        said, scope = clientimport.apply(self.cfg, result, self._world_tools(), add_world=add_world, trust=trust,
                                         world_name=world_name)
        self._save_settings()
        for line in said:
            self.system(line)
        if scope:
            self.system("The imported rules work in the world called '%s'." % scope)
        return said
