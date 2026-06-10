---
title: 2.3. Shortcuts
source: shortcuts.html
tags: [doublecmd, documentation]
---

# 2.3. Shortcuts

## Content

- 1. [[Keyboard Layout#1. Introduction|Introduction]]
- 2. [[Keyboard Layout#2. Main window|Main window]]
- 3. [[Keyboard Layout#3. Copy/Move Dialog|Copy/Move Dialog]]
- 4. [[Keyboard Layout#4. Edit Comment Dialog|Edit Comment Dialog]]
- 5. [[Keyboard Layout#5. Find Files|Find Files]]
- 6. [[Keyboard Layout#6. Multi-Rename Tool|Multi-Rename Tool]]
- 7. [[Keyboard Layout#7. Synchronize Directories|Synchronize Directories]]
- 8. [[Keyboard Layout#8. Internal Viewer|Internal viewer]]
- 9. [[Keyboard Layout#9. Internal Editor|Internal editor]]
- 10. [[Keyboard Layout#10. Differ|Differ]]
- 11. [[Keyboard Layout#11. Configuration|Configuration]]
  - 11.1. [[Keyboard Layout#11.1. Keys > Hot Keys|Keys > Hot Keys]]
  - 11.2. [[Keyboard Layout#11.2. Favorite Tabs|Favorite Tabs]]
  - 11.3. [[Keyboard Layout#11.3. Directory Hotlist|Directory Hotlist]]

## 1. Introduction

The following tables contain default keyboard shortcuts of Double Commander.

Most of them we can change by opening Configuration > Options... > Keys > [[Configuration#^ConfigHotKeys|Hot keys]] (or we can use the internal command [[Internal Commands#cm_ConfigHotKeys]]).

## 2. Main window

| Main Window |  |
| --- | --- |
| Key | Action |
| F1 | Open the program help |
| F2, Shift+F6 | Rename file under cursor.<br> 2. If nothing is selected and the cursor is on the first item (".."): edit current path (as [[Internal Commands#cm_EditPath]]). |
| F3 | 1. On file: open file for view in [[File Viewer\|internal viewer]] (multiple files are OK too).<br> 2. On directory: open this directory. |
| Shift+F3 | Open only the file under the cursor in internal viewer (if more than one file is selected) |
| F4 | Open file in editor, see details [[Internal Commands#cm_Edit\|here]] |
| Shift+F4 | Create a new text file and open in the internal editor or open existing file |
| F5 | Copy items from source to target |
| Shift+F5 | Copy items in the same directory ("inline") |
| F6 | Rename or move items |
| F7 | Create new directory |
| F8, Del | Delete selected files/folders to trash (recycle bin), see [[Configuration#^ConfigOperations\|Delete to recycle bin (Shift key reverses this setting)]] |
| Shift+F8, Shift+Del | Delete selected files/folders permanently, see [[Configuration#^ConfigOperations\|Delete to recycle bin (Shift key reverses this setting)]] |
| F9 | Starts a terminal |
| Alt+F1 | Change left drive |
| Alt+F2 | Change right drive |
| Alt+F4, Alt+X | Exit |
| Alt+F5 | Pack selected files |
| Alt+F7 | Find files |
| Alt+F8 | Invoke command line history pop up menu |
| Alt+F9 | Unpack all files from archive under cursor |
| Alt+digit (1..9) | Activate tab by index (see [[Internal Commands#cm_ActivateTabByIndex]]) |
| Alt+0 | Activate last tab (see [[Internal Commands#cm_ActivateTabByIndex]]) |
| Alt+ ↓ | Directory history |
| Alt+ ← | Go to previous entry in history |
| Alt+ → | Go to next entry in history |
| Alt+Shift+F9 | Validate the integrity of the content of selected archive file |
| Alt+Enter | File properties |
| Alt+Shift+Enter | Calculate size of all directories |
| Alt+Del | Wipe file/directory |
| Alt+V | Shows a window with the file operations process currently in progress if any |
| Alt+Z | Open the directory of the active panel in the opposite panel (Target=Source) |
| Ctrl+F1 | Brief view |
| Ctrl+F2 | Columns view |
| Ctrl+Shift+F1 | Thumbnails view |
| Ctrl+F3 | Sort by name |
| Ctrl+F4 | Sort by extension |
| Ctrl+F5 | Sort by date/time |
| Ctrl+F6 | Sort by size |
| Ctrl+digit (1..9) | Open drive by index (see [[Internal Commands#cm_OpenDriveByIndex]]) |
| Ctrl+Alt+Enter | Will invoke a program for the selected file from the system file associations |
| Ctrl+Tab | Goto next tab in the active panel |
| Ctrl+Shift+Tab | Goto previous tab in the active panel |
| Ctrl+A | Select all |
| Ctrl+B | Flat view: will scan all subdirectories in the current directory of the active panel and show all files in one list. Calling the command again will return to the normal mode. |
| Ctrl+Shift+B | Flat view: like `Ctrl+B`, but for selected files and folders only |
| Ctrl+C | Copy to clipboard |
| Ctrl+D | Directory hotlist |
| Ctrl+H | Invoke directory history drop-down menu |
| Ctrl+L | Calculate occupied space (for selected items) |
| Ctrl+M | Multi-Rename Tool |
| Ctrl+O | Toggle fullscreen mode console |
| Ctrl+P | Append active panel path to command line |
| Ctrl+Q | Quick view: content of selected item shown in opposite panel (see details [[File Viewer\|here]]) |
| Ctrl+R | Refresh actual panel |
| Ctrl+S | Quick search (see Options) |
| Ctrl+T | New tab in active panel |
| Ctrl+U | Swap panels (directory in left panel swaps with directory in right panel) |
| Ctrl+V | Paste from clipboard |
| Ctrl+W | Close actual tab |
| Ctrl+X | Cut to clipboard |
| Ctrl+Z | Create/edit file comment |
| Ctrl+ ↑ | Open selected directory at new tab |
| Ctrl+ ↓ | Invoke command line history pop up menu |
| Ctrl+ ← | Cursor in right panel, open same directory in left panel |
| Ctrl+ → | Cursor in left panel, open same directory in right panel |
| Ctrl+\ | Go to root directory ("/" in Unix-like OS) or root of the current disk (Windows).<br> In archive: go to root of this archive. |
| Ctrl+. | Show/hide hidden and system files |
| Ctrl+Enter | Append selected item to command line |
| Ctrl+Shift+Enter | Append concatenation of active panel path and selected item to command line |
| Ctrl+Shift+F7 | New search instance |
| Ctrl+Shift+F8 | Tree view panel |
| Ctrl+Shift+Home | Change directory to home |
| Ctrl+Shift+A | Show a menu with a list of all open tabs |
| Ctrl+Shift+C | Copy full names of selected items to clipboard |
| Ctrl+Shift+X | Copy names of selected items to clipboard |
| Ctrl+Shift+D | Configuration of Directory Hotlist |
| Ctrl+Shift+H | Will set the arrangement of panels between two vertical ones disposed in left/right OR two horizontal ones disposed in top/bottom |
| Ctrl+PgDn | 1. Like `Enter`.<br> 2. Open directory/archive (also self extracting archives). |
| Ctrl+PgUp | Like `Backspace` |
| Ctrl+Num + | Select all |
| Ctrl+Num - | Unselect all |
| Num + | Expand selection |
| Num - | Shrink selection |
| Num * | Invert selection |
| Shift+Num + | Select all files in the current directory with the same extension as the focused file |
| Shift+Num - | Unselect all files in the current directory with the same extension as the focused file |
| Shift+F2 | Set focus to command line |
| Shift+F10 | Show context menu for files and folders |
| Shift+F12 | Will show window with all internal commands |
| Shift+Tab | Switch focus between current file list and tree view (if enabled) |
| Shift+Enter | Execute command in terminal (choose in Options..) |
| Tab | Switch between panels |
| Enter | 1. The cursor is in the command line and it is not empty: execute the command.<br> 2. The cursor is on a directory/archive: open the directory/archive.<br> 3. The cursor is on an executable file: run it.<br> 4. The cursor is on a regular file: open in the associated program.<br> 5. The cursor is on a file inside an archive: show the properties dialog of the packed file or unpack the file from the archive and run it or open in the associated program.<br> 6. The cursor is on a checksum file: perform checksum verification.<br> 7. The cursor is in the edit field when renaming in the file panel: save the new name. |
| Insert | Select file or directory |
| Backspace | Goto to the upper (parent) directory |
| Space | 1. On file - select / deselect item.<br> 2. On directory - select / deselect item and compute space occupied in dir. |
| alphanumeric keys | The action depends on the [[Configuration#^ConfigKeys\|settings]] |
| Left/right arrows← | Go to upper directory or go to selected directory (if [[Configuration#^ConfigKeys\|Lynx like movement]] enabled and only in the full mode).<br> Brief or thumbnails mode: move cursor horizontally to previous/next column or move cursor horizontally to previous/next thumbnail. |
| Right mouse button | Show popup menu with configurable commands (from [[Configuration#^ConfigAssociations\|file associations]]) |

## 3. Copy/Move Dialog

| Copy/Move Dialog |  |
| --- | --- |
| Key | Action |
| F2 | Add a task to the queue of file operations |
| F5, F6 | Toggle selection in field with target directory and file name (in a circle):<br> filename without extension > filename with extension > file extension > path > select all |

## 4. Edit Comment Dialog

| Edit Comment Dialog |  |
| --- | --- |
| Key | Action |
| F2 | Save description |

## 5. Find Files

| Find Files |  |
| --- | --- |
| Key | Action |
| Esc | Cancel search and close window |
| F3 | View (for found files on the "Result" page) |
| F4 | Edit (for found files on the "Result" page) |
| F7 | Enables searching by file contents and switches focus |
| F9 | Start |
| Alt+1, Alt+F7 | Go to page "Standard" |
| Alt+2 | Go to page "Advanced" |
| Alt+3 | Go to page "Plugins" |
| Alt+4 | Go to page "Load/Save" |
| Alt+5 | Go to page "Results" |
| Ctrl+Tab | Switch to Next Page |
| Ctrl+Shift+Tab | Switch to Previous Page |
| Alt+F4 | Cancel search, close and free from memory |
| Ctrl+L | Last search |
| Ctrl+N | New search |
| Ctrl+Shift+N | New search (clear filters) |

## 6. Multi-Rename Tool

| Multi-Rename Tool |  |
| --- | --- |
| Key | Action |
| Esc | Close |
| F2 | Show presets list |
| F3 | Load names from file |
| F4 | Edit names |
| Shift+F4 | Edit current new names |
| F9 | Rename |
| F10 | Configuration |
| F11 | View rename log file |
| F12 | Save preset with specified name |
| Alt+0 | Load last preset |
| Alt+digit (1..9) | Load preset by index: 1st, 2nd and so on |
| Ctrl+F1 | File name: show submenu with plugin fields |
| Ctrl+Shift+F1 | Extension: show submenu with plugin fields |
| Ctrl+F2 | File name: show menu with placeholders |
| Ctrl+Shift+F2 | Extension: show menu with placeholders |
| Ctrl+F3 | File name: show the submenu of placeholders "Name" |
| Ctrl+Shift+F3 | Extension: show the submenu of placeholders "Name" |
| Ctrl+F4 | File name: show the submenu of placeholders "Extension" |
| Ctrl+Shift+F4 | Extension: show the submenu of placeholders "Extension" |
| Ctrl+F5 | File name: show the submenu of placeholders "Date" |
| Ctrl+Shift+F5 | Extension: show the submenu of placeholders "Date" |
| Ctrl+F6 | File name: show the submenu of placeholders "Time" |
| Ctrl+Shift+F6 | Extension: show the submenu of placeholders "Time" |
| Ctrl+F7 | File name: show the submenu of placeholders "Counter" |
| Ctrl+Shift+F7 | Extension: show the submenu of placeholders "Counter" |
| Ctrl+Shift+S | Sort presets |
| Ctrl+D | Delete preset |
| Ctrl+I | Show menu "Editor" |
| Ctrl+R | Reset all (return default state) |
| Ctrl+S | Save modified preset |
| Shift+F2 | Show preset menu |
| Shift+F6 | Rename preset |

## 7. Synchronize Directories

| Synchronize Directories |  |
| --- | --- |
| Key | Action |
| F3 | View left |
| Shift+F3 | View right |
| Ctrl+F3 | Compare files by contents |
| Ctrl+D | Select for copying (default direction) |
| Ctrl+L | Select for copying -> (left to right) |
| Ctrl+R | Select for copying <- (right to left) |
| Ctrl+M | Remove selection |
| Ctrl+W | Reverse copy direction |

## 8. Internal Viewer

| Internal Viewer |  |
| --- | --- |
| Key | Action |
| Esc, Q (or with any combination Ctrl, Shift, Alt) | Close |
| F2 | Reload current file |
| F6 | Show/hide text cursor |
| F7, Ctrl+F7, Ctrl+F | Find text |
| F3 | Find next |
| Shift+F3 | Find previous |
| Alt+Enter | Full Screen |
| Ctrl+A | Select All |
| Ctrl+C | Copy selected text to clipboard |
| Ctrl+G | Go to the specified line (only in code view mode) |
| Ctrl+P | Print |
| Ctrl+Z | Undo (only in image viewing mode) |
| 1 | Show as text |
| 2 | Show as bin |
| 3 | Show as hex |
| 4 | Show as dec |
| 5 | Show as Book |
| 6 | Show as graphic |
| 7 | Show using plugin |
| 8 | Office XML (DOCX and XLSX, ODT and ODS), text only |
| 9 | Show in code view mode |
| A | Change encoding: ANSI |
| S | Change encoding: OEM |
| X | Change encoding: UTF-16 LE |
| Z | Change encoding: UTF-8 |
| C | Image: place in the center of the window |
| F | Image: stretch image |
| L | Image: stretch only large |
| N, Alt+ → | Next file in multiple files |
| P, Alt+ ← | Previous file in multiple files |
| W | Wrap/unwrap text |
| Num + | Zoom In |
| Num - | Zoom Out |
| ` | Show/hide preview |

## 9. Internal Editor

Some hotkeys are not configurable!

| Internal Editor |  |
| --- | --- |
| Key | Action |
| Esc, Alt+X | Quit |
| F2, Ctrl+S | Save |
| F7, Ctrl+F | Find text |
| F3 | Find next |
| Shift+F3 | Find previous |
| Backspace | Delete from left |
| Ctrl+Backspace | Delete from left by words |
| Del | Delete from right |
| Home | Move the cursor to the beginning of the line |
| End | Move the cursor to the end of the line |
| PgDn | Scroll content down page by page |
| PgUp | Scroll content up page by page |
| Insert | Toggle insert/overwrite mode |
| Alt+Backspace | Undo |
| Alt+Shift+Backspace | Redo |
| Ctrl+digit (0..9) | Go to bookmark |
| Ctrl+Shift+digit (0..9) | Set bookmark |
| Ctrl+↑ | Scroll the content up along with moving the text cursor: the cursor will remain in the lowest visible line in the editor window |
| Ctrl+↓ | Scroll the content down along with moving the text cursor: the cursor will remain in the topmost visible line in the editor window |
| Ctrl+← | Move the cursor to the previous word |
| Ctrl+→ | Move the cursor to the next word |
| Ctrl+Home | Move the cursor to the beginning of the file |
| Ctrl+End | Move the cursor to the end of the file |
| Ctrl+PgDn | Move the cursor to the lowest visible line in the editor window |
| Ctrl+PgUp | Move the cursor to the topmost visible line in the editor window |
| Ctrl+Shift+← | Select left by words |
| Ctrl+Shift+→ | Select right by words |
| Ctrl+Shift+Home | Select text up to the beginning of the file |
| Ctrl+Shift+End | Select text up to the end of the file |
| Ctrl+Shift+PgDn | Select text up to the lowest visible line in the editor window |
| Ctrl+Shift+PgUp | Select text up to the topmost visible line in the editor window |
| Ctrl+A | Select All |
| Ctrl+C | Copy selected text to clipboard |
| Ctrl+G | Go to the specified line |
| Ctrl+N | Create a new file |
| Ctrl+O | Open file |
| Ctrl+R | Replace text |
| Ctrl+T | Delete from right by words |
| Ctrl+V | Paste text from clipboard |
| Ctrl+X | Cut selected text to clipboard |
| Ctrl+Y | Delete line |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z | Redo |
| Ctrl+Shift+C | Column selection mode |
| Ctrl+Shift+L | Line selection mode |
| Ctrl+Shift+N | Normal selection mode |
| Ctrl+Shift+B | Move the cursor to matching bracket ("()", "[]" or "{}") |
| Ctrl+Shift+I | Add an indent for a line or block of text |
| Ctrl+Shift+U | Remove an indent for a line or block of text |
| Ctrl+Shift+Y | Delete text up to the end of the line. |
| Ctrl+Insert | Copy |
| Shift+↑ | Extend selection to the same column in the previous line |
| Shift+↓ | Extend selection to the same column in the next line |
| Shift+← | Select left |
| Shift+→ | Select right |
| Shift+Home | Select text up to the beginning of the line |
| Shift+End | Select text up to the end of the line |
| Shift+PgDn | Select one page down |
| Shift+PgUp | Select one page up |
| Shift+Del | Delete |
| Shit+Insert | Paste |
| Tab | 1. Insert a Tab charater.<br> 2. If [[Configuration#^ConfigToolsEditor\|Tab indents blocks]] is enabled and text is selected: add an indent for a line or block of text. |
| Shift+Tab | If [[Configuration#^ConfigToolsEditor\|Tab indents blocks]] is enabled and text is selected: remove an indent for a line or block of text |

Inside an open document, you can paste a copy of the selected text anywhere in the document without using the clipboard: just select the text, move the mouse cursor to the desired position and press the mouse wheel.

Internal editor supports multi-carets mode: mouse selection with the `Alt` key, `Alt+Shift+click` or `Alt+Shift+arrows` for column editing and `Ctrl+Shift+click` for multi-carets editing.

| Text column selection hotkeys |  |
| --- | --- |
| Key | Action |
| Alt+Shift+↑ | Column select up |
| Alt+Shift+↓ | Column select down |
| Alt+Shift+← | Column select left |
| Alt+Shift+→ | Column select right |
| Alt+Shift+Home | Column select line start |
| Alt+Shift+End | Column select line end |
| Alt+Shift+PgDn | Column select page down |
| Alt+Shift+PgUp | Column select page up |
| Ctrl+Alt+Shift+Home | Column select up to the beginning of the file |
| Ctrl+Alt+Shift+End | Column select up to the end of the file |
| Ctrl+Alt+Shift+PgDn | Column select page down |
| Ctrl+Alt+Shift+PgUp | Column select page up |

Note: If the contents of more than one line are selected, the indent change commands do not work correctly, this is a limitation of the component used.

## 10. Differ

| Differ |  |
| --- | --- |
| Key | Action |
| F7, Ctrl+F | Find text |
| F3 | Find next |
| Shift+F3 | Find previous |
| Alt+Home | First difference |
| Alt+End | Last difference |
| Alt+ ↑ | Previous difference |
| Alt+ ↓ | Next difference |
| Alt+ ← | Copy block left |
| Alt+ → | Copy block right |
| Alt+X | Close |
| Ctrl+G | Go to the specified line |
| Ctrl+R | Reload files |

## 11. Configuration

In the configuration pages, some of them have many possible actions to be done during the configuration, that some shorcut keys are present to help us to quickly do what needs to be done.

These ones are not reconfigurable but at least there are present by default and the following table will list them.

The `F1` key will open the corresponding section of the Double Commander help.

## 11.1. Keys > Hot Keys

| Keys > Hot Keys |  |
| --- | --- |
| Key | Action |
| F4 | Edit hotkey for the command under the cursor |
| F5 | Copy the current set of hotkeys |
| F7 | Add hotkey for the command under the cursor |
| F8 | Delete the current set of hotkeys |
| F9 | Make popup the hotkey file related menu |
| Del | Delete hotkey for the command under the cursor |
| Num + | Next category |
| Num - | Previous category |
| Ctrl+F3 | Sort a list of commands by command name |
| Ctrl+F4 | Sort a list of commands by hotkeys (grouped) |
| Ctrl+F5 | Sort a list of commands by hotkeys (one per row) |
| Ctrl+S | Save the current set of hotkeys |
| Shift+F6 | Rename the current set of hotkeys |
| Shift+Ctrl+R | Restore DC default |

## 11.2. Favorite Tabs

| Favorite Tabs |  |
| --- | --- |
| Key | Action |
| F2 | Sort single group of item(s) only |
| F6 | Rename |
| F7 | Add sub-menu |
| Shift+F7 | Insert sub-menu |
| F10 | Add separator |
| Shift+F10 | Insert separator |
| Del | Delete selected item |
| Ctrl+X | Cut |
| Ctrl+V | Paste |

## 11.3. Directory Hotlist

To help us to configure our [[Directory Hotlist|directory hotlist]], we have plenty of shortcut keys.

This allows us to remain with the focus in the bottom three boxes to enter our names and path, and still being able to move into the hotlist tree without quitting the text box.

| Directory Hotlist |  |
| --- | --- |
| Key | Action |
| F2 | Will move focus on the directory hotlisty tree |
| F5 | Insert a duplicate copy of the current selected entry at the current position |
| F7 | Insert a submenu at the current position |
| F8 | Delete the current entry at the selection position |
| F9 | Insert an entry with a directory we will type at the current position |
| F10 | Insert an horizontal separator line at the current position |
| Ctrl+F5 | Add a duplicate copy of the current selected entry below the current position |
| Ctrl+F7 | Insert a submenu below the current position |
| Ctrl+F8 | Delete the selected elements, but when a sub menu is met, will delete the submenu entry point, but all the content will not be deleted and will be move one level closer to the root |
| Ctrl+F9 | Insert an entry with a directory we will type below the current position |
| Ctrl+F10 | Insert an horizontal separator line below the current position |
| Ctrl+Home | Will set the selection to first element of the list |
| Ctrl+End | Will set the selection to the last displayable entry without having to open a new branch |
| Ctrl+ ← | If the current selection is sub menu entry, the branch will be closed |
| Ctrl+ → | If the current selection is sub menu entry, the branch will be opened |
| Ctrl+ ↑ | Will move the current selection above the current position |
| Ctrl+ ↓ | Will move the current selection below the current position |
| Ctrl+Shift+F8 | Delete the selected elements and if a sub menu is met, will delete the whole thing as well |
| Ctrl+Shift+Alt+F8 | Delete all the elements, no matter if selected or not |
| Ctrl+Shift+P | Will allow to edit the path of the current selection to make it relative to something or many other offered options |
| Ctrl+Shift+T | Will allow to edit the path of the current selection to make it relative to something or many other offered options |
| Ctrl+Shift+V | Will erase the entries that were place in the temporary list with the command described here just after, and will paste them to the current new position |
| Ctrl+Shift+X | Will save in a temporary list the current selection ready to be removed and place somewhere else with the previous described command of this table |
| ↑ | Will set the selection to the entry just above the current one |
| ↓ | Will set the section to the entry just below the current ones |

---

[[Indice|← Index]]
