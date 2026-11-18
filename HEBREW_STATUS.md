# Hebrew and RTL implementation status

The goal is a Hebrew-first GridCraft Android app: Hebrew interface text, right-to-left navigation where appropriate, correct mixed Hebrew/Latin text, and reliable Hebrew editing inside cells and formulas.

## Source and language catalog

- The build uses the reviewed Hebrew/RTL source candidate at the immutable commit `ba06ef38575a1725a78e0d9099161f5c65db3646`.
- The Hebrew catalog contains the current UI catalog keys, but its own source describes it as a first pass, largely machine-assisted. A native Hebrew language review is still required before calling the translation finished.
- The Android/native build can use Android system-font fallback for Hebrew glyphs.
- The web build does not automatically select Hebrew because it does not yet guarantee an allowed Hebrew font face.

## Android-specific fixes applied during the build

The app-specific preparation script applies guarded, repeatable fixes to the pinned source:

- Imported/pathless workbooks are not silently changed when the interface language changes.
- Sheet-direction synchronization is deferred while an Undo group is open and is retried after the group ends or rolls back.
- Language changes update the engine's default sheet direction immediately, before subsequent commands in the same control batch.
- RTL Backstage forms get a vertical, right-aligned layout.
- Ribbon overflow measurements are isolated per tab.
- Snapshot test commands report malformed JSON rather than silently running with empty parameters.
- The macOS native-menu receiver remains alive when language changes rebuild the menu.
- Sheet-tab controls and status ordering receive an initial RTL layout pass; sheet reorder direction is mirrored.

## Items that still require verification or completion

This is **not yet a claim of complete Hebrew parity**. Before describing the app as fully Hebrew, the following must be checked and completed:

1. Review the Hebrew catalog with a fluent Hebrew editor for terminology, spelling, punctuation, and consistency with spreadsheet conventions.
2. Audit all dialogs, context menus, native prompts, settings, messages, and mixed Hebrew/Latin labels for bidi ordering and right-aligned field layout.
3. Test the sheet-tab strip, scrollbar, status bar, ribbon overflow, formula bar, name box, and selection indicators on real Android screen sizes and with touch input.
4. Verify Hebrew input-method composition, Backspace/Delete, cursor movement, selection, copy/paste, formula editing, and save/reopen round-trips in XLSX.
5. Verify formulas and function names: the current formula locale is not a Hebrew formula-syntax translation. Formula names and separators must retain the spreadsheet format expected by GridCraft and Excel.
6. Verify startup language selection and persistence on Android. Hebrew must be the initial language on a Hebrew-configured device, and a user-selected language must remain selected after restart.

## Test gate

A successful APK compile alone does not prove full Hebrew support. The release gate must include:
- Rust tests for document provenance and direction changes around undo groups.
- UI/i18n tests and a missing-translation report.
- An Android debug APK build and inspection of the actual interface.
- Hebrew typing/editing and XLSX open/save tests on the target device.
- Only after those checks: a signed release APK and verification of its fixed GitHub Release asset.
