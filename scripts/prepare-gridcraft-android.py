#!/usr/bin/env python3
"""Apply the GridCraft-specific Hebrew/RTL Android compatibility fixes to a pinned source tree.

The script is deliberately strict and idempotent:
- It never downloads or copies application source.
- Every replacement is tied to the reviewed source shape.
- It writes nothing until every patch anchor has been validated.
- It aborts if the pinned source has drifted unexpectedly.
"""
from __future__ import annotations

import sys
from pathlib import Path

if len(sys.argv) not in (2, 3):
    raise SystemExit("Usage: prepare-gridcraft-android.py <checked-out-gridcraft-source> [<artcraft-android-builder>]")

ROOT = Path(sys.argv[1]).resolve()
BUILDER_ROOT = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else None
if not (ROOT / "Cargo.toml").is_file() or not (ROOT / "crates/ui-egui/src/i18n.rs").is_file():
    raise SystemExit(f"Not a GridCraft workspace: {ROOT}")
if BUILDER_ROOT is not None and not (BUILDER_ROOT / "build.sh").is_file():
    raise SystemExit(f"Not an ArtCraft Android Builder checkout: {BUILDER_ROOT}")

pending: dict[Path, str] = {}
changed: list[str] = []
already: list[str] = []


def patch(relative: str, old: str, new: str, label: str) -> None:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"[GridCraft Hebrew] Required file is missing: {relative}")
    current = pending.get(path)
    if current is None:
        current = path.read_text(encoding="utf-8")

    if new in current:
        already.append(label)
        pending[path] = current
        return

    count = current.count(old)
    if count != 1:
        raise SystemExit(
            f"[GridCraft Hebrew] Refusing to patch {relative}: expected one exact anchor "
            f"for '{label}', found {count}. The pinned source may have changed."
        )

    pending[path] = current.replace(old, new, 1)
    changed.append(label)


# 1. Only genuinely new local workbooks may inherit a language-driven sheet direction.
patch(
    "crates/engine/src/lib.rs",
    "    pub fn is_untouched_new(&self) -> bool {\n"
    "        self.path.is_none() && !self.is_dirty() && self.undo.is_empty() && self.redo.is_empty()\n"
    "    }",
    "    pub fn is_untouched_new(&self) -> bool {\n"
    "        self.trust == Trust::Local && self.path.is_none() && !self.is_dirty() && self.undo.is_empty() && self.redo.is_empty()\n"
    "    }",
    "restrict automatic direction changes to session-created workbooks",
)

# 2. Defer direction sync for documents with an open undo group. Apply the preference again
#    once the outer group ends or rolls back, so saved state and undo baselines stay consistent.
patch(
    "crates/engine/src/lib.rs",
    "    /// Sets the direction new sheets read in, and turns the sheets of new workbooks nobody has\n"
    "    /// changed yet to it; opened and edited workbooks keep their own.\n"
    "    pub fn set_default_right_to_left(&mut self, on: bool) {\n"
    "        self.prefs.default_right_to_left = on;\n"
    "        for d in &mut self.docs {\n"
    "            d.follow_direction(on);\n"
    "        }\n"
    "    }",
    "    /// Applies the saved default direction to eligible documents, but never while one of their\n"
    "    /// undo groups is open: a group owns its original workbook and saved-state baseline.\n"
    "    fn sync_default_right_to_left(&mut self) {\n"
    "        let on = self.prefs.default_right_to_left;\n"
    "        let grouped: Vec<u64> = self.groups.iter().map(|group| group.doc).collect();\n"
    "        let mut changed = Vec::new();\n"
    "        for document in &mut self.docs {\n"
    "            if !grouped.contains(&document.uid) {\n"
    "                let before = document.wb.clone();\n"
    "                document.follow_direction(on);\n"
    "                if !Arc::ptr_eq(&before, &document.wb) {\n"
    "                    changed.push(document.uid);\n"
    "                }\n"
    "            }\n"
    "        }\n"
    "        // A clean direction-only change is not an undo step. Keep a non-stepped group marker\n"
    "        // aligned with the new workbook so a later edit does not compare against stale state.\n"
    "        if let Some(step) = self.group_step.as_mut().filter(|step| !step.stepped && changed.contains(&step.doc))\n"
    "            && let Some(document) = self.docs.iter().find(|document| document.uid == step.doc)\n"
    "        {\n"
    "            step.after = document.wb.clone();\n"
    "            step.selection = document.selection.clone();\n"
    "            step.len = document.undo.len();\n"
    "        }\n"
    "    }\n"
    "\n"
    "    /// Sets the direction new sheets read in, and turns the sheets of new workbooks nobody has\n"
    "    /// changed yet to it; opened and edited workbooks keep their own.\n"
    "    pub fn set_default_right_to_left(&mut self, on: bool) {\n"
    "        self.prefs.default_right_to_left = on;\n"
    "        self.sync_default_right_to_left();\n"
    "    }",
    "defer sheet direction synchronization around undo groups",
)

patch(
    "crates/engine/src/lib.rs",
    "        if self.depth == 0 {\n"
    "            self.trim_history();\n"
    "        }\n"
    "        Ok(changed)\n"
    "    }\n",
    "        if self.depth == 0 {\n"
    "            self.trim_history();\n"
    "        }\n"
    "        self.sync_default_right_to_left();\n"
    "        Ok(changed)\n"
    "    }\n",
    "resync eligible workbook directions after ending an undo group",
)

patch(
    "crates/engine/src/lib.rs",
    "        if !kept && !self.groups.iter().any(|o| o.doc == g.doc) {\n"
    "            self.group_step = Some(GroupStep { doc: g.doc, after: d.wb.clone(), selection: d.selection.clone(), len: g.start, stepped: false });\n"
    "        }\n"
    "        Ok(())\n"
    "    }\n",
    "        if !kept && !self.groups.iter().any(|o| o.doc == g.doc) {\n"
    "            self.group_step = Some(GroupStep { doc: g.doc, after: d.wb.clone(), selection: d.selection.clone(), len: g.start, stepped: false });\n"
    "        }\n"
    "        self.sync_default_right_to_left();\n"
    "        Ok(())\n"
    "    }\n",
    "resync eligible workbook directions after rolling back an undo group",
)

# 3. Regression coverage for imported pathless documents and deferred direction changes.
patch(
    "crates/engine/tests/it/default_direction.rs",
    "use gridcraft_engine::Session;\n",
    "use gridcraft_engine::{DocState, Session, Trust};\n"
    "use gridcraft_engine::model::Workbook;\n",
    "import document provenance types for direction tests",
)
patch(
    "crates/engine/tests/it/default_direction.rs",
    "    assert_eq!(directions(&session, next), [true, true], \"inserting a sheet changed it\");\n"
    "}\n",
    "    assert_eq!(directions(&session, next), [true, true], \"inserting a sheet changed it\");\n"
    "}\n"
    "\n"
    "#[test]\n"
    "fn a_pathless_imported_workbook_does_not_follow_interface_direction() {\n"
    "    let imported = DocState::new(Workbook::new(), None, \"Imported\".into(), Trust::FromFile);\n"
    "    assert!(!imported.is_untouched_new(), \"a pathless import is still from a file\");\n"
    "    let local = DocState::new(Workbook::new(), None, \"Book1\".into(), Trust::Local);\n"
    "    assert!(local.is_untouched_new(), \"a newly created local workbook may follow the interface\");\n"
    "}\n"
    "\n"
    "#[test]\n"
    "fn direction_sync_waits_for_an_open_undo_group_and_stays_clean_after_rollback() {\n"
    "    let mut session = Session::new();\n"
    "    let document = session.new_workbook();\n"
    "    let token = session.group_begin(\"direction test\").unwrap();\n"
    "    session.set_default_right_to_left(true);\n"
    "    assert_eq!(directions(&session, document), [false], \"the open group's baseline is untouched\");\n"
    "    session.group_rollback(token).unwrap();\n"
    "    assert_eq!(directions(&session, document), [true], \"the deferred direction is applied after rollback\");\n"
    "    assert!(!session.documents()[document].is_dirty(), \"direction sync is not a workbook edit\");\n"
    "}\n",
    "test imported workbooks and undo-group direction synchronization",
)

# 4. Language commands must update the engine immediately, before another command in the same
#    control batch can create a sheet using the stale direction.
patch(
    "crates/ui-egui/src/control.rs",
    "fn run(app: &mut SheetApp, id: &str, params: Json) -> Result<Json, String> {\n"
    "    let r = app.run(id, params);\n"
    "    if r.is_ok() && matches!(id, \"edit.goTo\" | \"edit.goToSpecial\" | \"selection.set\" | \"selection.move\") {\n"
    "        app.grid.ensure_visible = true;\n"
    "    }\n"
    "    r\n"
    "}",
    "fn run(app: &mut SheetApp, id: &str, params: Json) -> Result<Json, String> {\n"
    "    let r = app.run(id, params);\n"
    "    if r.is_ok() && matches!(id, \"app.language.set\" | \"app.language.english\" | \"app.language.japanese\") {\n"
    "        app.session.set_default_right_to_left(app.ui.language.is_rtl());\n"
    "    }\n"
    "    if r.is_ok() && matches!(id, \"edit.goTo\" | \"edit.goToSpecial\" | \"selection.set\" | \"selection.move\") {\n"
    "        app.grid.ensure_visible = true;\n"
    "    }\n"
    "    r\n"
    "}",
    "apply language direction immediately in the control channel",
)

patch(
    "crates/ui-egui/src/ribbon/controls.rs",
    "pub(super) fn act(app: &mut SheetApp, id: &str, params: serde_json::Value) {\n"
    "    app.run_or_alert(id, params);\n"
    "}",
    "pub(super) fn act(app: &mut SheetApp, id: &str, params: serde_json::Value) {\n"
    "    app.run_or_alert(id, params);\n"
    "    if matches!(id, \"app.language.set\" | \"app.language.english\" | \"app.language.japanese\") {\n"
    "        app.session.set_default_right_to_left(app.ui.language.is_rtl());\n"
    "    }\n"
    "}",
    "apply language direction immediately after a ribbon language change",
)

# 5. RTL Backstage forms need a vertical parent layout; otherwise rows can flow side by side
#    when the helper is called from an existing horizontal layout.
patch(
    "crates/ui-egui/src/backstage.rs",
    "        let mut form = Form { ui, rtl, spacing, label_w, widest: 0.0 };\n"
    "        rows(&mut form);\n"
    "        let widest = form.widest;\n",
    "        let available = vec2(ui.available_width(), ui.available_height());\n"
    "        let response = ui.allocate_ui_with_layout(available, egui::Layout::top_down(egui::Align::Max), |ui| {\n"
    "            let mut form = Form { ui, rtl, spacing, label_w, widest: 0.0 };\n"
    "            rows(&mut form);\n"
    "            form.widest\n"
    "        });\n"
    "        let widest = response.inner;\n",
    "lay out RTL Backstage form rows vertically and right-aligned",
)

# 6. Keep ribbon measurements isolated by tab; a wide tab must not force blank width into a
#    different tab when RTL uses the previous frame's natural group measurement.
patch(
    "crates/ui-egui/src/ribbon.rs",
    "                let last = RibbonOverflow::get(ui.ctx());\n",
    "                let last = RibbonOverflow::get(ui.ctx(), tab.as_str());\n",
    "read the active tab's own ribbon measurement",
)
patch(
    "crates/ui-egui/src/ribbon.rs",
    "impl RibbonOverflow {\n"
    "    /// Returns the stable id for the ribbon overflow state.\n"
    "    fn id() -> egui::Id {\n"
    "        egui::Id::unique(\"ribbon_overflow\")\n"
    "    }",
    "impl RibbonOverflow {\n"
    "    /// Returns a stable id for this tab's ribbon overflow state.\n"
    "    fn id(tab: &str) -> egui::Id {\n"
    "        egui::Id::unique((\"ribbon_overflow\", tab))\n"
    "    }",
    "use a per-tab ribbon overflow state key",
)
patch(
    "crates/ui-egui/src/ribbon.rs",
    "    pub fn get(ctx: &egui::Context) -> RibbonOverflow {\n"
    "        ctx.data(|d| d.get_temp(Self::id())).unwrap_or_default()\n"
    "    }",
    "    pub fn get(ctx: &egui::Context, tab: &str) -> RibbonOverflow {\n"
    "        ctx.data(|d| d.get_temp(Self::id(tab))).unwrap_or_default()\n"
    "    }",
    "read a tab-scoped ribbon overflow state",
)
patch(
    "crates/ui-egui/src/ribbon.rs",
    "    ui.ctx().data_mut(|d| d.insert_temp(RibbonOverflow::id(), overflow));\n",
    "    ui.ctx().data_mut(|d| d.insert_temp(RibbonOverflow::id(tab), overflow));\n",
    "write a tab-scoped ribbon overflow state",
)


def patch_many(relative: str, old: str, new: str, expected: int, label: str) -> None:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"[GridCraft Hebrew] Required file is missing: {relative}")
    current = pending.get(path)
    if current is None:
        current = path.read_text(encoding="utf-8")

    old_count = current.count(old)
    new_count = current.count(new)
    if old_count == 0 and new_count == expected:
        already.append(label)
        pending[path] = current
        return
    if old_count != expected:
        raise SystemExit(
            f"[GridCraft Hebrew] Refusing to patch {relative}: expected {expected} "
            f"occurrences for '{label}', found {old_count} old and {new_count} new."
        )
    pending[path] = current.replace(old, new)
    changed.append(label)


# Keep the ribbon integration tests compatible with the per-tab overflow state above. The
# harness already records its selected tab, so the helper always queries that tab's measurement.
patch(
    "crates/ui-egui/tests/it/ribbon_layout.rs",
    "    h.run_steps(4);\n"
    "    h\n"
    "}\n",
    "    h.run_steps(4);\n"
    "    h\n"
    "}\n\n"
    "fn ribbon_overflow(h: &Harness) -> RibbonOverflow {\n"
    "    RibbonOverflow::get(&h.ctx, &h.state().ui.ribbon_tab)\n"
    "}\n",
    "add a test helper for per-tab ribbon overflow",
)
patch_many(
    "crates/ui-egui/tests/it/ribbon_layout.rs",
    "RibbonOverflow::get(&h.ctx)",
    "ribbon_overflow(&h)",
    10,
    "update ribbon layout tests to query the active tab",
)
patch_many(
    "crates/ui-egui/tests/it/ribbon_layout.rs",
    "RibbonOverflow::get(&app_at(700.0, t).ctx)",
    "ribbon_overflow(&app_at(700.0, t))",
    1,
    "update ribbon tab discovery test to query its own tab",
)


# 7. Report malformed snapshot JSON instead of silently running the action with empty parameters.
patch(
    "crates/ui-egui/examples/snapshot.rs",
    "use serde_json::json;\n\n"
    "fn main() {",
    "use serde_json::json;\n\n"
    "fn parse_action(raw: &str) -> Option<(&str, serde_json::Value)> {\n"
    "    let Some((id, params)) = raw.split_once('=') else {\n"
    "        return Some((raw, json!({})));\n"
    "    };\n"
    "    match serde_json::from_str(params) {\n"
    "        Ok(params) => Some((id, params)),\n"
    "        Err(error) => {\n"
    "            eprintln!(\"Invalid JSON parameters for snapshot action {id:?}: {error}\");\n"
    "            None\n"
    "        }\n"
    "    }\n"
    "}\n\n"
    "fn main() {",
    "add strict snapshot action argument parsing",
)
patch(
    "crates/ui-egui/examples/snapshot.rs",
    "    for c in &cmds {\n"
    "        let (id, p) = c.split_once('=').map(|(a, b)| (a.to_string(), serde_json::from_str(b).unwrap_or(json!({})))).unwrap_or((c.clone(), json!({})));\n"
    "        if let Err(e) = session.execute(&id, p) {\n"
    "            eprintln!(\"{id}: {e}\");\n"
    "        }\n"
    "    }",
    "    for c in &cmds {\n"
    "        let Some((id, params)) = parse_action(c) else { continue };\n"
    "        if let Err(error) = session.execute(id, params) {\n"
    "            eprintln!(\"{id}: {error}\");\n"
    "        }\n"
    "    }",
    "reject malformed snapshot engine command parameters",
)
patch(
    "crates/ui-egui/examples/snapshot.rs",
    "                for c in &app_cmds {\n"
    "                    let (id, p) =\n"
    "                        c.split_once('=').map(|(a, b)| (a, serde_json::from_str(b).unwrap_or(json!({})))).unwrap_or((c.as_str(), json!({})));\n"
    "                    if let Err(e) = app.run(id, p) {\n"
    "                        eprintln!(\"{id}: {e}\");\n"
    "                    }\n"
    "                }",
    "                for c in &app_cmds {\n"
    "                    let Some((id, params)) = parse_action(c) else { continue };\n"
    "                    if let Err(error) = app.run(id, params) {\n"
    "                        eprintln!(\"{id}: {error}\");\n"
    "                    }\n"
    "                }",
    "reject malformed snapshot app command parameters",
)
patch(
    "crates/ui-egui/examples/snapshot.rs",
    "                if let Some(d) = &dialog {\n"
    "                    let (name, p) =\n"
    "                        d.split_once('=').map(|(a, b)| (a, serde_json::from_str(b).unwrap_or(json!({})))).unwrap_or((d.as_str(), json!({})));\n"
    "                    app.open_dialog(name, p);\n"
    "                }",
    "                if let Some(d) = &dialog\n"
    "                    && let Some((name, params)) = parse_action(d)\n"
    "                {\n"
    "                    app.open_dialog(name, params);\n"
    "                }",
    "reject malformed snapshot dialog parameters",
)

# 8. A native menu handler is process-wide in muda 0.21.2. Keep one receiver alive while
#    language changes replace the menu objects; drain it from whichever menu is current.
patch(
    "apps/gridcraft/src/native_menu.rs",
    "use std::str::FromStr;\n"
    "use std::sync::mpsc::{Receiver, channel};\n",
    "use std::str::FromStr;\n"
    "use std::sync::mpsc::{Receiver, channel};\n"
    "use std::sync::{Mutex, OnceLock};\n",
    "import process-wide native menu event state",
)
patch(
    "apps/gridcraft/src/native_menu.rs",
    "pub struct NativeMenu {\n"
    "    _menu: Menu,\n"
    "    /// The interface language the labels are in; a new language rebuilds the menu bar.\n"
    "    pub language: Language,\n"
    "    events: Receiver<MenuEvent>,\n"
    "    theme_items: Vec<(&'static str, CheckMenuItem)>,",
    "static MENU_EVENTS: OnceLock<Mutex<Receiver<MenuEvent>>> = OnceLock::new();\n\n"
    "fn install_menu_event_handler(ctx: &egui::Context) {\n"
    "    MENU_EVENTS.get_or_init(|| {\n"
    "        let (sender, receiver) = channel();\n"
    "        let repaint_context = ctx.clone();\n"
    "        MenuEvent::set_event_handler(Some(move |event: MenuEvent| {\n"
    "            let _ = sender.send(event);\n"
    "            repaint_context.request_repaint();\n"
    "        }));\n"
    "        Mutex::new(receiver)\n"
    "    });\n"
    "}\n\n"
    "fn drain_menu_events() -> Vec<MenuEvent> {\n"
    "    MENU_EVENTS\n"
    "        .get()\n"
    "        .and_then(|receiver| receiver.lock().ok().map(|receiver| receiver.try_iter().collect()))\n"
    "        .unwrap_or_default()\n"
    "}\n\n"
    "pub struct NativeMenu {\n"
    "    _menu: Menu,\n"
    "    /// The interface language the labels are in; a new language rebuilds the menu bar.\n"
    "    pub language: Language,\n"
    "    theme_items: Vec<(&'static str, CheckMenuItem)>,",
    "use one process-wide menu event handler and receiver",
)
patch(
    "apps/gridcraft/src/native_menu.rs",
    "        let (tx, rx) = channel();\n"
    "        let ctx = ctx.clone();\n"
    "        MenuEvent::set_event_handler(Some(move |e: MenuEvent| {\n"
    "            let _ = tx.send(e);\n"
    "            ctx.request_repaint();\n"
    "        }));\n"
    "        NativeMenu { _menu: menu, language, events: rx, theme_items, window_menu, window_items: Vec::new(), windows: Vec::new() }",
    "        install_menu_event_handler(ctx);\n"
    "        NativeMenu { _menu: menu, language, theme_items, window_menu, window_items: Vec::new(), windows: Vec::new() }",
    "avoid replacing the process-wide menu event receiver on language change",
)
patch(
    "apps/gridcraft/src/native_menu.rs",
    "        while let Ok(ev) = self.events.try_recv() {\n"
    "            let id = ev.id.as_ref().to_string();",
    "        for ev in drain_menu_events() {\n"
    "            let id = ev.id.as_ref().to_string();",
    "drain events from the persistent native menu channel",
)

# 9. The web build lacks a guaranteed Hebrew face. Do not auto-select an unreadable Hebrew
#    catalog there; native Android uses system-font fallback and remains eligible for Hebrew.
patch(
    "apps/gridcraft-web/src/web.rs",
    "                    // Follow the browser's language, except a CJK one. CJK coverage comes from\n"
    "                    // optional craft-fonts input, not a guaranteed web font set, so a CJK browser\n"
    "                    // cannot be assumed to render localized labels without tofu. Users can still\n"
    "                    // choose a language explicitly.\n"
    "                    let browser = gridcraft_ui_egui::i18n::Language::system();\n"
    "                    if !matches!(\n"
    "                        browser,\n"
    "                        gridcraft_ui_egui::i18n::Language::Zh | gridcraft_ui_egui::i18n::Language::Ja | gridcraft_ui_egui::i18n::Language::Ko\n"
    "                    ) {\n",
    "                    // Follow the browser's language except scripts whose faces are not guaranteed\n"
    "                    // in the web build: CJK needs optional craft-fonts, and Hebrew has no web-allowed\n"
    "                    // face yet. Users can still choose an available language explicitly.\n"
    "                    let browser = gridcraft_ui_egui::i18n::Language::system();\n"
    "                    if !matches!(\n"
    "                        browser,\n"
    "                        gridcraft_ui_egui::i18n::Language::Zh\n"
    "                            | gridcraft_ui_egui::i18n::Language::Ja\n"
    "                            | gridcraft_ui_egui::i18n::Language::Ko\n"
    "                            | gridcraft_ui_egui::i18n::Language::He\n"
    "                    ) {\n",
    "avoid automatic Hebrew selection in web builds without Hebrew fonts",
)

# 10. Android installs should start in Hebrew, while desktop builds keep their English
#     default. The normal persisted UI preference still takes precedence after the first launch.
patch(
    "crates/ui-egui/src/lib.rs",
    "            language: i18n::Language::En,\n",
    "            language: if cfg!(target_os = \"android\") { i18n::Language::He } else { i18n::Language::En },\n",
    "default fresh Android installs to Hebrew without changing the desktop default",
)

# 10. The sheet tabs and status row should follow the Hebrew shell's visual direction. The
#     horizontal workbook data itself stays governed by each sheet's own right_to_left flag.
patch(
    "crates/ui-egui/src/tabs.rs",
    "    egui::Panel::bottom(\"sheet_tabs\").exact_size(32.0).frame(egui::Frame::NONE.fill(t.tab_bar)).show(ui, |ui| {\n"
    "        let rect = ui.max_rect();\n"
    "        ui.painter().line_segment([rect.left_top(), rect.right_top()], Stroke::new(1.0, t.ribbon_border));\n"
    "        ui.horizontal_centered(|ui| {",
    "    let rtl = app.ui.language.is_rtl();\n"
    "    egui::Panel::bottom(\"sheet_tabs\").exact_size(32.0).frame(egui::Frame::NONE.fill(t.tab_bar)).show(ui, |ui| {\n"
    "        let rect = ui.max_rect();\n"
    "        ui.painter().line_segment([rect.left_top(), rect.right_top()], Stroke::new(1.0, t.ribbon_border));\n"
    "        let row_layout = if rtl { egui::Layout::right_to_left(egui::Align::Center) } else { egui::Layout::left_to_right(egui::Align::Center) };\n"
    "        ui.scope_builder(egui::UiBuilder::new().layout(row_layout), |ui| {\n"
    "        ui.horizontal_centered(|ui| {",
    "mirror the sheet-tab strip container for RTL languages",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                if crate::widgets::icon_button(ui, Icon::Left, t.text_dim, app.ui.language.tr(\"Previous sheet\"), vec2(24.0, 24.0)).clicked() {",
    "                if crate::widgets::icon_button(ui, if rtl { Icon::Right } else { Icon::Left }, t.text_dim, app.ui.language.tr(\"Previous sheet\"), vec2(24.0, 24.0)).clicked() {",
    "mirror the previous-sheet navigation icon",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                if crate::widgets::icon_button(ui, Icon::Right, t.text_dim, app.ui.language.tr(\"Next sheet\"), vec2(24.0, 24.0)).clicked() {",
    "                if crate::widgets::icon_button(ui, if rtl { Icon::Left } else { Icon::Right }, t.text_dim, app.ui.language.tr(\"Next sheet\"), vec2(24.0, 24.0)).clicked() {",
    "mirror the next-sheet navigation icon",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                ui.allocate_ui_with_layout(vec2(tabs_width, 30.0), egui::Layout::left_to_right(egui::Align::Center), |ui| {",
    "                let tabs_layout = if rtl { egui::Layout::right_to_left(egui::Align::Center) } else { egui::Layout::left_to_right(egui::Align::Center) };\n"
    "                ui.allocate_ui_with_layout(vec2(tabs_width, 30.0), tabs_layout, |ui| {",
    "mirror the worksheet-tab contents for RTL languages",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                                        let dx = p.x - r.center().x;\n",
    "                                        let dx = if rtl { r.center().x - p.x } else { p.x - r.center().x };\n",
    "preserve logical sheet-reorder direction in RTL",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "            crate::grid::horizontal_scrollbar(app, ui, track, &t);\n"
    "        });\n"
    "    });\n"
    "}",
    "            crate::grid::horizontal_scrollbar(app, ui, track, &t);\n"
    "        });\n"
    "        });\n"
    "    });\n"
    "}",
    "close RTL sheet-tab layout scope",
)

patch(
    "crates/ui-egui/src/tabs.rs",
    "            ui.horizontal_centered(|ui| {\n"
    "                let mode = match app.session.mode {",
    "            let rtl = app.ui.language.is_rtl();\n"
    "            let status_layout = if rtl { egui::Layout::right_to_left(egui::Align::Center) } else { egui::Layout::left_to_right(egui::Align::Center) };\n"
    "            ui.scope_builder(egui::UiBuilder::new().layout(status_layout), |ui| {\n"
    "            ui.horizontal_centered(|ui| {\n"
    "                let mode = match app.session.mode {",
    "mirror status-bar ordering for RTL languages",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                        text(ui, egui::RichText::new(\"Macros preserved (not executed)\").font(theme::ui_font(12.5)).color(t.danger));",
    "                        text(ui, egui::RichText::new(app.ui.language.tr(\"Macros preserved (not executed)\")).font(theme::ui_font(12.5)).color(t.danger));",
    "translate the macro-preservation status message",
)
patch(
    "crates/ui-egui/src/tabs.rs",
    "                });\n"
    "            });\n"
    "        },\n"
    "    );\n"
    "}\n",
    "                });\n"
    "            });\n"
    "            });\n"
    "        },\n"
    "    );\n"
    "}\n",
    "close RTL status-bar layout scope",
)

patch(
    "crates/ui-egui/src/i18n/he.rs",
    "        \"Largest to Smallest\" => \"מהגדול לקטן\",\n",
    "        \"Macros preserved (not executed)\" => \"פקודות מאקרו נשמרו (לא הופעלו)\",\n"
    "        \"Largest to Smallest\" => \"מהגדול לקטן\",\n",
    "translate macro-preservation status text into Hebrew",
)

patch(
    "docs/localization-parity.md",
    "| Hebrew | he | ~1398 (every key any catalog has; first pass, mostly machine-assisted) | dialogs, menus, File view, macOS menu bar, equation messages | Hebrew via the system fallback face; title bar, ribbon tabs and groups, File view and new sheets read right to left; sheet tabs, status bar, dialogs and mixed Hebrew/Latin labels stay left to right | no | full catalog, needs review | 8–14 h |",
    "| Hebrew | he | ~1398 (every key any catalog has; first pass, mostly machine-assisted) | dialogs, menus, File view, macOS menu bar, equation messages | Native builds use system-font fallback; web builds do not auto-select Hebrew until a web-allowed Hebrew face exists. Title bar, ribbon and File view read right to left; sheet tabs and status ordering are mirrored in this Android port; dialogs and mixed Hebrew/Latin labels still need a full bidi/layout audit | no | full catalog, needs native-speaker review and remaining RTL dialog work | 8–14 h |",
    "document the actual Hebrew and web font boundaries",
)

# 11. Mobile UI and Android input compatibility.
# Backstage pages need both axes on compact portrait screens, and Options should open in a
# screen-sized modal instead of being squeezed into the narrow backstage content column.
patch(
    "crates/ui-egui/src/backstage.rs",
    "        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {\n",
    "        egui::ScrollArea::both().auto_shrink([false, false]).show(ui, |ui| {\n",
    "allow horizontal and vertical scrolling in Backstage pages",
)
patch(
    "crates/ui-egui/src/backstage.rs",
    "                        Page::Options => options(app, ui),\n",
    "                        Page::Options => {},\n",
    "render Options in the responsive modal rather than the narrow page column",
)
patch(
    "crates/ui-egui/src/backstage.rs",
    "    });\n"
    "    bs.text_edit_focused = ctx.text_edit_focused();\n",
    "    });\n"
    "    if bs.page == Page::Options {\n"
    "        let screen = ctx.content_rect();\n"
    "        let modal_size = vec2(\n"
    "            (screen.width() - 24.0).clamp(220.0, 900.0),\n"
    "            (screen.height() - 24.0).clamp(260.0, 1200.0),\n"
    "        );\n"
    "        let mut close = false;\n"
    "        let response = egui::Modal::new(egui::Id::new(\"gridcraft-options-modal\")).show(&ctx, |ui| {\n"
    "            ui.set_min_size(modal_size);\n"
    "            ui.set_max_size(modal_size);\n"
    "            let layout = if rtl { egui::Layout::right_to_left(egui::Align::Center) } else { egui::Layout::left_to_right(egui::Align::Center) };\n"
    "            ui.with_layout(layout, |ui| {\n"
    "                ui.label(RichText::new(lang.tr(\"Options\")).font(theme::ui_font(22.0)).color(t.text));\n"
    "                ui.add_space(12.0);\n"
    "                if ui.button(lang.tr(\"Close\")).clicked() { close = true; }\n"
    "            });\n"
    "            ui.separator();\n"
    "            egui::ScrollArea::vertical()\n"
    "                .id_salt(\"gridcraft-options-modal-scroll\")\n"
    "                .auto_shrink([false, false])\n"
    "                .show(ui, |ui| options(app, ui));\n"
    "        });\n"
    "        if close || response.should_close() {\n"
    "            out.close = true;\n"
    "        }\n"
    "    }\n"
    "    bs.text_edit_focused = ctx.text_edit_focused();\n",
    "open Options in a responsive scrollable modal",
)
patch(
    "crates/ui-egui/src/grid/show.rs",
    "    let previous_popups = (app.grid.filter_menu, app.grid.list_picker, app.grid.header_menu, app.grid.fill_menu);\n"
    "    // A pan the grid never saw end (it was hidden mid-drag) must not swallow the next press.\n"
    "    if app.grid.touch_pan && !resp.dragged() && !resp.drag_stopped() {\n"
    "        app.grid.touch_pan = false;\n"
    "    }\n"
    "    if app.grid.touch_pan {\n"
    "        // Skip the frames of a touch pan, its release included.\n"
    "        if !resp.dragged() {\n"
    "            app.grid.touch_pan = false;\n"
    "        }\n"
    "    } else {\n"
    "        crate::paper_view::interact(app, ui, resp, geo, sh, wb);\n"
    "        interact(app, ui, resp, geo, sh, wb);\n"
    "    }\n",
    "    let previous_popups = (app.grid.filter_menu, app.grid.list_picker, app.grid.header_menu, app.grid.fill_menu);\n"
    "    // The Android backend cancels the first touch when a two-finger pan/pinch takes over.\n"
    "    // Drop any cell/object drag that began with that first finger, otherwise scrolling can\n"
    "    // accidentally extend a cell selection or move an object under the gesture.\n"
    "    let touch_gesture_cancelled = ui.input(|i| i.events.iter().any(|event| {\n"
    "        matches!(event, egui::Event::Touch { phase: egui::TouchPhase::Cancel, .. })\n"
    "    }));\n"
    "    if touch_gesture_cancelled {\n"
    "        app.grid.drag = Drag::None;\n"
    "        app.grid.drag_select = false;\n"
    "        app.grid.touch_pan = false;\n"
    "    } else if app.grid.touch_pan && !resp.dragged() && !resp.drag_stopped() {\n"
    "        // A pan the grid never saw end (it was hidden mid-drag) must not swallow the next press.\n"
    "        app.grid.touch_pan = false;\n"
    "    }\n"
    "    if touch_gesture_cancelled {\n"
    "        // The backend already emitted the scroll/zoom event; do not feed the cancelled press\n"
    "        // into grid selection, object dragging or paper interaction.\n"
    "    } else if app.grid.touch_pan {\n"
    "        // Skip the frames of a one-finger touch pan, its release included.\n"
    "        if !resp.dragged() {\n"
    "            app.grid.touch_pan = false;\n"
    "        }\n"
    "    } else {\n"
    "        crate::paper_view::interact(app, ui, resp, geo, sh, wb);\n"
    "        interact(app, ui, resp, geo, sh, wb);\n"
    "    }\n",
    "cancel in-progress grid selection when the Android backend takes over for touch scrolling",
)
# GridCraft-specific patching of the shared Android launcher/IME bridge. This is limited to
# the builder checkout supplied by the GridCraft workflow; it does not change any other app.
def patch_builder(relative: str, old: str, new: str, label: str) -> None:
    if BUILDER_ROOT is None:
        raise SystemExit(f"[GridCraft Android] Builder checkout required for '{label}'.")
    path = BUILDER_ROOT / relative
    if not path.is_file():
        raise SystemExit(f"[GridCraft Android] Required builder file is missing: {relative}")
    current = pending.get(path)
    if current is None:
        current = path.read_text(encoding="utf-8")
    if new in current:
        already.append(label)
        pending[path] = current
        return
    count = current.count(old)
    if count != 1:
        raise SystemExit(
            f"[GridCraft Android] Refusing to patch {relative}: expected one exact anchor "
            f"for '{label}', found {count}."
        )
    pending[path] = current.replace(old, new, 1)
    changed.append(label)

patch_builder(
    "templates/android/SafActivity.java",
    "    public void onImeDelete() {\n"
    "        imeQueue.add(\"\\b\");\n"
    "        wakeNativeLoop();\n"
    "    }\n",
    "    public void onImeDelete() {\n"
    "        imeQueue.add(\"\\b\");\n"
    "        wakeNativeLoop();\n"
    "    }\n\n"
    "    /** Forward an IME's range deletion as one structured edit, not repeated Backspace keys. */\n"
    "    public void onImeDeleteSurrounding(int beforeChars, int afterChars) {\n"
    "        if (beforeChars < 0 || afterChars < 0 || (beforeChars == 0 && afterChars == 0)) return;\n"
    "        int before = Math.min(beforeChars, 4000);\n"
    "        int after = Math.min(afterChars, 4000);\n"
    "        imeQueue.add(String.valueOf((char) 1) + \"DS:\" + before + \":\" + after);\n"
    "        wakeNativeLoop();\n"
    "    }\n",
    "forward Android IME surrounding deletion from the Activity",
)
patch_builder(
    "templates/android/SafActivity.java",
    "                @Override\n"
    "                public Editable getEditable() {\n"
    "                    return editable;\n"
    "                }\n\n"
    "                @Override\n"
    "                public boolean sendKeyEvent(KeyEvent event) {",
    "                @Override\n"
    "                public Editable getEditable() {\n"
    "                    return editable;\n"
    "                }\n\n"
    "                // Android reports surrounding lengths in UTF-16 units, while egui edits\n"
    "                // Unicode characters. Convert only when the requested range is in the\n"
    "                // current shadow buffer; otherwise retain Android's count as a safe fallback.\n"
    "                private int codePointsBefore(int utf16Units) {\n"
    "                    int start = Selection.getSelectionStart(editable);\n"
    "                    int end = Selection.getSelectionEnd(editable);\n"
    "                    if (start < 0 || end < 0 || start != end || start > editable.length() || utf16Units > start) return utf16Units;\n"
    "                    int from = start - utf16Units;\n"
    "                    if (from > 0 && from < start && Character.isLowSurrogate(editable.charAt(from)) && Character.isHighSurrogate(editable.charAt(from - 1))) from--;\n"
    "                    return Character.codePointCount(editable, from, start);\n"
    "                }\n\n"
    "                private int codePointsAfter(int utf16Units) {\n"
    "                    int start = Selection.getSelectionStart(editable);\n"
    "                    int end = Selection.getSelectionEnd(editable);\n"
    "                    if (start < 0 || end < 0 || start != end || end > editable.length() || utf16Units > editable.length() - end) return utf16Units;\n"
    "                    int to = end + utf16Units;\n"
    "                    if (to > 0 && to < editable.length() && Character.isHighSurrogate(editable.charAt(to - 1)) && Character.isLowSurrogate(editable.charAt(to))) to++;\n"
    "                    return Character.codePointCount(editable, end, to);\n"
    "                }\n\n"
    "                private boolean forwardDeleteSurrounding(int beforeLength, int afterLength, boolean codePoints) {\n"
    "                    if (beforeLength < 0 || afterLength < 0) return false;\n"
    "                    if (beforeLength == 0 && afterLength == 0) return true;\n"
    "                    int beforeChars = codePoints ? beforeLength : codePointsBefore(beforeLength);\n"
    "                    int afterChars = codePoints ? afterLength : codePointsAfter(afterLength);\n"
    "                    boolean wasSuppressing = ArtCraftInputView.this.suppressingWatcher;\n"
    "                    ArtCraftInputView.this.suppressingWatcher = true;\n"
    "                    try {\n"
    "                        if (codePoints) super.deleteSurroundingTextInCodePoints(beforeLength, afterLength);\n"
    "                        else super.deleteSurroundingText(beforeLength, afterLength);\n"
    "                    } finally {\n"
    "                        ArtCraftInputView.this.suppressingWatcher = wasSuppressing;\n"
    "                    }\n"
    "                    onImeDeleteSurrounding(beforeChars, afterChars);\n"
    "                    return true;\n"
    "                }\n\n"
    "                @Override\n"
    "                public boolean deleteSurroundingText(int beforeLength, int afterLength) {\n"
    "                    return forwardDeleteSurrounding(beforeLength, afterLength, false);\n"
    "                }\n\n"
    "                @Override\n"
    "                public boolean deleteSurroundingTextInCodePoints(int beforeLength, int afterLength) {\n"
    "                    return forwardDeleteSurrounding(beforeLength, afterLength, true);\n"
    "                }\n\n"
    "                @Override\n"
    "                public boolean sendKeyEvent(KeyEvent event) {",
    "forward correct UTF-16/code-point deletion ranges to egui",
)
patch_builder(
    "vendor/egui-winit/src/lib.rs",
    "use raw_window_handle::HasDisplayHandle;\n",
    "use raw_window_handle::HasDisplayHandle;\n\n"
    "/// Decode the private Android IME bridge message for DeleteSurrounding.\n"
    "#[cfg(any(target_os = \"android\", test))]\n"
    "fn parse_android_delete_surrounding(value: &str) -> Option<(usize, usize)> {\n"
    "    let payload = value.strip_prefix(\"\\u{1}DS:\")?;\n"
    "    let (before, after) = payload.split_once(':')?;\n"
    "    if after.contains(':') { return None; }\n"
    "    let before = before.parse::<usize>().ok()?;\n"
    "    let after = after.parse::<usize>().ok()?;\n"
    "    (before <= 4000 && after <= 4000).then_some((before, after))\n"
    "}\n\n"
    "#[cfg(test)]\n"
    "mod android_ime_bridge_tests {\n"
    "    use super::parse_android_delete_surrounding;\n"
    "    #[test]\n"
    "    fn parses_bounded_delete_surrounding_requests() {\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:1:0\"), Some((1, 0)));\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:4:2\"), Some((4, 2)));\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:0:0\"), Some((0, 0)));\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:4001:0\"), None);\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:-1:0\"), None);\n"
    "        assert_eq!(parse_android_delete_surrounding(\"\\u{1}DS:1\"), None);\n"
    "        assert_eq!(parse_android_delete_surrounding(\"ordinary text\"), None);\n"
    "    }\n"
    "}\n",
    "add a bounded Android IME DeleteSurrounding message decoder and tests",
)
patch_builder(
    "vendor/egui-winit/src/lib.rs",
    "            for ev in crate::ime::android::poll_all_ime_events() {\n"
    "                if ev == \"\\x08\" {\n",
    "            for ev in crate::ime::android::poll_all_ime_events() {\n"
    "                if let Some((before_chars, after_chars)) = parse_android_delete_surrounding(&ev) {\n"
    "                    self.egui_input.events.push(egui::Event::Ime(egui::ImeEvent::DeleteSurrounding {\n"
    "                        before_chars,\n"
    "                        after_chars,\n"
    "                    }));\n"
    "                } else if ev == \"\\x08\" {\n",
    "deliver Android IME range deletion as egui DeleteSurrounding",
)


# The shared launcher normally follows the physical sensor. GridCraft must instead honor
# Android's user rotation setting, matching the verified WordCraft behavior.
patch_builder(
    "lib/build-common.sh",
    '    config_changes = "orientation|keyboard|keyboardHidden|navigation|screenSize|screenLayout|smallestScreenSize|density|layoutDirection|uiMode|fontScale|locale"',
    '    config_changes = "orientation|keyboard|keyboardHidden|navigation|screenSize|screenLayout|smallestScreenSize|density|layoutDirection|uiMode|fontScale|locale"'
    + "\\n" + '    screen_orientation = "user" if app == "gridcraft" else "sensor"',
    "honor Android user rotation preference for GridCraft",
)

# The builder emits the activity block in two shapes (SAF and non-SAF apps); both
# must receive the per-app orientation value. Validate exactly two anchors.
def patch_builder_many(relative: str, old: str, new: str, expected: int, label: str) -> None:
    if BUILDER_ROOT is None:
        raise SystemExit(f"[GridCraft Android] Builder checkout required for '{label}'.")
    path = BUILDER_ROOT / relative
    if not path.is_file():
        raise SystemExit(f"[GridCraft Android] Required builder file is missing: {relative}")
    current = pending.get(path)
    if current is None:
        current = path.read_text(encoding="utf-8")
    if old not in current and current.count(new) == expected:
        already.append(label)
        pending[path] = current
        return
    count = current.count(old)
    if count != expected:
        raise SystemExit(
            f"[GridCraft Android] Refusing to patch {relative}: expected {expected} exact anchors "
            f"for '{label}', found {count}."
        )
    pending[path] = current.replace(old, new)
    changed.append(label)

patch_builder_many(
    "lib/build-common.sh",
    'orientation = "sensor"',
    'orientation = "{screen_orientation}"',
    2,
    "apply user-controlled rotation in both Android launcher manifest templates",
)

# 12. Commit all changes only after every source and builder anchor has been verified.
for path, text in pending.items():
    if path.exists():
        path.write_text(text, encoding="utf-8")

print(f"[GridCraft Hebrew] Applied {len(changed)} source patches; {len(already)} were already present.")
for label in changed:
    print(f"  patched: {label}")
for label in already:
    print(f"  unchanged: {label}")
