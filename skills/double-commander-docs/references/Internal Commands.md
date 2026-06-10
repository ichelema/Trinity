---
title: 2.13. Internal Commands
source: cmds.html
tags: [doublecmd, documentation]
---

# 2.13. Internal Commands

## Content

- 1. [[Internal Commands#1. Table of Command Categories|Table of Command Categories]]
- 2. [[Internal Commands#2. Description of all commands per category|Description of all commands by category]]
  - 2.1. [[Internal Commands#2.1. Active Panel|Active Panel]]
  - 2.2. [[Internal Commands#2.2. Left Panel|Left Panel]]
  - 2.3. [[Internal Commands#2.3. Right Panel|Right Panel]]
  - 2.4. [[Internal Commands#2.4. File Operations|File Operations]]
  - 2.5. [[Internal Commands#2.5. Configuration|Configuration]]
  - 2.6. [[Internal Commands#2.6. Network|Network]]
  - 2.7. [[Internal Commands#2.7. Miscellaneous|Miscellaneous]]
  - 2.8. [[Internal Commands#2.8. Mark|Mark]]
  - 2.9. [[Internal Commands#2.9. Clipboard|Clipboard]]
  - 2.10. [[Internal Commands#2.10. Navigation|Navigation]]
  - 2.11. [[Internal Commands#2.11. Help|Help]]
  - 2.12. [[Internal Commands#2.12. Window|Window]]
  - 2.13. [[Internal Commands#2.13. Command Line|Command Line]]
  - 2.14. [[Internal Commands#2.14. Tools|Tools]]
  - 2.15. [[Internal Commands#2.15. View|View]]
  - 2.16. [[Internal Commands#2.16. Tabs|Tabs]]
  - 2.17. [[Internal Commands#2.17. Logs|Logs]]

## 1. Table of Command Categories

Internal commands may be groups by categories so here they are:

| Table of Command Categories |  |
| --- | --- |
| Category | Description |
| [[Internal Commands#2.1. Active Panel\|Active Panel]] | These commands apply to the **current selected panel**, left or right. |
| [[Internal Commands#2.2. Left Panel\|Left Panel]] | These commands apply to the **left panel**, no matter which one is currently selected. |
| [[Internal Commands#2.3. Right Panel\|Right Panel]] | These commands apply to the **right panel**, no matter which one is currently selected. |
| [[Internal Commands#2.4. File Operations\|File Operations]] | These commands apply to current selected item in current selected panel.<br>It includes operations like view/copy/move/rename/delete/pack/unpack/split, etc.<br>These are the commands that can have a **direct impact on your files**. |
| [[Internal Commands#2.5. Configuration\|Configuration]] | Access options and configurations of Double Commander. |
| [[Internal Commands#2.6. Network\|Network]] | Related directly with computer network. |
| [[Internal Commands#2.7. Miscellaneous\|Miscellaneous]] | Inevitable category with those commands which we did not know in which category to place them!<br>Effort has been made to try not to place too many commands in this category. |
| [[Internal Commands#2.8. Mark\|Mark]] | Select the items on which file operations will take place. |
| [[Internal Commands#2.9. Clipboard\|Clipboard]] | Interaction between the system clipboard and selected items. |
| [[Internal Commands#2.10. Navigation\|Navigation]] | To move from one folder to another to access different items according to their location. |
| [[Internal Commands#2.11. Help\|Help]] | Access the integrated help files of Double Commander. |
| [[Internal Commands#2.12. Window\|Window]] | Commands related to the Double Commander window, its look and behaviour like any other computer application. |
| [[Internal Commands#2.13. Command Line\|Command line]] | Interact with command line to view past commands and help to invoke new ones. |
| [[Internal Commands#2.14. Tools\|Tools]] | For action requiring more than a click. These action will generally show another window to have Double Commander do some more complex jobs. |
| [[Internal Commands#2.15. View\|View]] | Commands related with the visibility and appearance of data files, system files, etc. |
| [[Internal Commands#2.16. Tabs\|Tabs]] | Interact with tabs by creating new ones, navigate from directory to directory, etc. |
| [[Internal Commands#2.17. Logs\|Logs]] | Actions related with DC log files. |

## 2. Description of all commands per category

Here is a quick description of all the internal command.

For each of them we will:

- list the command name
- display its icon
- when applicable, its default keyboard shortcut
- a quick description of it
- when applicable, quick description of possible parameters of it

## 2.1. Active Panel

These commands apply to the **current selected panel**, left or right.

### cm_BriefView

**Shortcut:** `Ctrl+F1`

Just the name of the items.

If possible, more than one column.

### cm_ColumnsView

**Shortcut:** `Ctrl+F2`

One item per line, with default or user defined columns.

| Parameter | Value | Description |
| --- | --- | --- |
| columnset | *column set name* | show user defined column set |
| *(nothing, default)* | show default column set |  |

See [[Configuration#^ConfigColumns|column section]].

### cm_ThumbnailsView

**Shortcut:** `Ctrl+Shift+F1`

Items shown as small images.

If possible, in more than one column.

### cm_FlatView

**Shortcut:** `Ctrl+B`

Will scan all subdirectories in the current directory of the panel and show all files in one list. Calling the command again will return to the normal mode.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | in left panel, as the [[Internal Commands#cm_LeftFlatView]] command |
| right | in right panel, as the [[Internal Commands#cm_RightFlatView]] command |  |
| inactive | in inactive panel |  |
| *(absent)* | in current active panel |  |
| *(nothing, default)* | in current active panel |  |

### cm_FlatViewSel

**Shortcut:** `Ctrl+Shift+B`

Like the cm_FlatView command without parameter, but for selected files and folders only.

### cm_QuickView

**Shortcut:** `Ctrl+Q`

Content of selected item shown in opposite panel (instead of a separate window).

See details [[File Viewer|here]].

### cm_SortByName

**Shortcut:** `Ctrl+F3`

Sort items in active panel by [[Basic Help#^cm_SortByName|name]].

### cm_SortByExt

**Shortcut:** `Ctrl+F4`

Sort items in active panel by [[Basic Help#^cm_SortByExt|extension]].

### cm_SortBySize

**Shortcut:** `Ctrl+F6`

Sort items in active panel by [[Basic Help#^cm_SortBySize|file size]].

### cm_SortByDate

**Shortcut:** `Ctrl+F5`

Sort items in active panel by [[Basic Help#^cm_SortByDate|date]].

### cm_SortByAttr

Sort items in active panel by [[Basic Help#^cm_SortByAttr|attributes]].

### cm_ReverseOrder

[[Basic Help#^cm_ReverseOrder|Invert sorting]] items displayed in the active panel.

### cm_SrcOpenDrives

Open drives list for active panel.

### cm_UniversalSingleDirectSort

Will sort specified column in specified order of the specified panel.

See the following table for the possible parameter values.

| Parameter | Value | Description |
| --- | --- | --- |
| panel | active | will operate on active panel |
| inactive | will operate on inactive panel |  |
| left | will operate on left panel |  |
| right | will operate on right panel |  |
| *(absent)* | will operate on active panel |  |
| column | name | sorted columns will be the "name-ext" |
| ext | sorted column will be the "ext" |  |
| size | sorted column will be the "size" |  |
| datetime | sorted column will be the "datetime" |  |
| *(absent)* | sorted column will be the "name" |  |
| order | ascending | will sort with ascending order |
| descending | will sort with descending order |  |
| *(absent)* | will sort with ascending order |  |
| Note: If any of these three parameters are not defined or are defined incorrectly; the default values for these parameters will be: panel=active, column=name and order=ascending. |  |  |

Example: "cm_UniversalSingleDirectSort panel=active column=size order=descending"

This will sort the item in active by column according to size – larger files first.

### cm_CountDirContent

**Shortcut:** `Alt+Shift+Enter`

Compute overall size of the contents of each of the directories present in current selected panel.

## 2.2. Left Panel

These commands apply to the **left panel**, no matter which one is currently selected.

### cm_LeftBriefView

In left panel, just the name of the items.

If possible, more than one column.

### cm_LeftColumnsView

In left panel, one item per line, with default or user defined columns.

| Parameter | Value | Description |
| --- | --- | --- |
| columnset | *column set name* | show user defined column set |
| *(nothing, default)* | show default column set |  |

See [[Configuration#^ConfigColumns|column section]].

### cm_LeftThumbView

In left panel, items shown as thumbnails.

If possible, more than one column.

### cm_LeftFlatView

Will scan all subdirectories in the current directory of the left panel and show all files in one list.

### cm_LeftSortByName

Sort items in left panel by [[Basic Help#^cm_SortByName|name]].

### cm_LeftSortByExt

Sort items in left panel by [[Basic Help#^cm_SortByExt|extension]].

### cm_LeftSortBySize

Sort items in left panel by [[Basic Help#^cm_SortBySize|size]].

### cm_LeftSortByDate

Sort items in left panel by [[Basic Help#^cm_SortByDate|date]].

### cm_LeftSortByAttr

Sort items in left panel by [[Basic Help#^cm_SortByAttr|attributes]].

### cm_LeftReverseOrder

[[Basic Help#^cm_ReverseOrder|Invert sorting]] items in the left panel.

### cm_LeftOpenDrives

**Shortcut:** `Alt+F1`

Open [[Basic Help#^cm_LeftOpenDrives|drives list]] for left panel.

## 2.3. Right Panel

These commands apply to the **right panel**, no matter which one is currently selected.

### cm_RightBriefView

In right panel, just the name of the items.

If possible, more than one column.

### cm_RightColumnsView

In right panel, one item per line, with default or user defined columns.

| Parameter | Value | Description |
| --- | --- | --- |
| columnset | *column set name* | show user defined column set |
| *(nothing, default)* | show default column set |  |

See [[Configuration#^ConfigColumns|column section]].

### cm_RightThumbView

In right panel, items shown as thumbnails.

If possible, more than one column.

### cm_RightFlatView

Will scan all subdirectories in the current directory of the right panel and show all files in one list.

### cm_RightSortByName

Sort items in right panel by [[Basic Help#^cm_SortByName|name]].

### cm_RightSortByExt

Sort items in right panel by [[Basic Help#^cm_SortByExt|extension]].

### cm_RightSortBySize

Sort items in right panel by [[Basic Help#^cm_SortBySize|size]].

### cm_RightSortByDate

Sort items in right panel by [[Basic Help#^cm_SortByDate|date]].

### cm_RightSortByAttr

Sort items in right panel by [[Basic Help#^cm_SortByAttr|attributes]].

### cm_RightReverseOrder

[[Basic Help#^cm_ReverseOrder|Invert sorting]] items in the right panel.

### cm_RightOpenDrives

**Shortcut:** `Alt+F2`

Open [[Basic Help#^cm_RightOpenDrives|drives list]] for right panel.

## 2.4. File Operations

These commands apply to current selected item in current selected panel.
It includes operations like view/copy/move/rename/delete/pack/unpack/split etc.
These are probably the commands that have a **direct impact with your files**.

### cm_View

**Shortcut:** `F3`

Open file in the [[File Viewer|viewer program]].

| Parameter | Value | Description |
| --- | --- | --- |
| cursor | 1/true/on/yes | open only the file under the cursor |
| 0/false/off/no | default behavior |  |
| mode | text | show as Text |
| bin | show as Bin |  |
| hex | show as Hex |  |
| dec | show as Dec |  |

The "mode" parameter allows to forcibly choose the viewing mode (in this case, plugins will be ignored, but we can switch the mode later in the viewer window), but this parameter will work under one of the conditions: there are no selected files, only the file under the cursor is selected, or together with the "cursor=1" parameter. See the description of the modes on [[File Viewer#2.3. "View"|this page]].

### cm_Edit

**Shortcut:** `F4`

Open file in editor (internal or external, see [[Configuration#^ConfigToolsEditor|Tools > Editor]]).

| Parameter | Value | Description |
| --- | --- | --- |
| cursor | 1/true/on/yes | open only the file under the cursor |
| 0/false/off/no | default behavior |  |

If several files are selected, the first selected file will be opened (as in the [[Internal Commands#cm_View|viewer]]): at the moment, the command's work with several selected files is not fully implemented, so you can deselect files, add "cursor=1" or use [[Internal Commands#cm_EditNew]].

### cm_EditNew

**Shortcut:** `Shift+F4`

Create a new text file in the current directory and open in the editor (see [[Configuration#^ConfigToolsEditor|Tools > Editor]]) or open existing file (if a file with the same name already exists).

 You can enter the full name of the file (with path) and it will be created in the specified directory.

### cm_Copy

**Shortcut:** `F5`

Copy items from source to target.

| Parameter | Value | Description |
| --- | --- | --- |
| confirmation | 1/true/on/yes | shows confirmation dialog (default) |
| 0/false/off/no | does not show a confirmation dialog |  |
| queueid | *<queue identifier>* | by default places the copy operation into a specific queue, works only if no confirmation dialog is shown, value 0 means it will be an independent operation (not queued) |

Example: "cm_Copy confirmation=1" will prompt user to confirm the copy, no matter how file operations confirmation for copy operations setting is set.

### cm_CopyNoAsk

Copy items from source to target without asking for confirmation.

### cm_CopySamePanel

**Shortcut:** `Shift+F5`

Copy items in the same directory.

### cm_Rename

**Shortcut:** `F6`

Rename or move items.

| Parameter | Value | Description |
| --- | --- | --- |
| confirmation | 1/true/on/yes | shows confirmation dialog (default) |
| 0/false/off/no | does not show a confirmation dialog |  |
| queueid | *<queue identifier>* | by default places the move operation into a specific queue, works only if no confirmation dialog is shown, value 0 means it will be an independent operation (not queued) |

Example: "cm_Rename confirmation=1" will prompt user to confirm the rename/move, no matter how file operations confirmation for move operations setting is set.

### cm_RenameNoAsk

Rename or move items without asking for confirmation.

### cm_RenameOnly

**Shortcut:** `F2, Shift+F6`

Rename files in the same directory.

### cm_MakeDir

**Shortcut:** `F7`

Create a new directory.

### cm_Delete

**Shortcut:** `F8, Del`

Delete selected item to trash (recycle bin) or permanently.

 Deleting to trash can might not be available for all platforms.

 A different confirmation message is given when deleting to trash or permanently.

| Parameter | Value | Description |
| --- | --- | --- |
| confirmation | 1/true/on/yes | shows confirmation dialog (default) |
| 0/false/off/no | does not show a confirmation dialog (be careful!) |  |
| trashcan | 1/true/on/yes | delete to trash |
| 0/false/off/no | delete permanently |  |
| setting | (default) acts accordingly to the global setting in [[Configuration#^ConfigOperations\|File Operations]], if that setting is enabled it will delete to trash, otherwise permanently |  |
| reversesetting | acts in the opposite way than setting |  |

### cm_Wipe

**Shortcut:** `Alt+Del`

[[Basic Help#^cm_Wipe|Wipe]] file.

### cm_PackFiles

**Shortcut:** `Alt+F5`

[[Basic Help#^cm_PackFiles|Pack]] items into archive.

| Parameter | Value | Description |
| --- | --- | --- |
| PackHere | *(nothing)* | compressed file will be in active panel directory |
| *(nothing, default)* | compressed file will be in inactive panel directory |  |

### cm_TestArchive

**Shortcut:** `Alt+Shift+F9`

Validate the integrity of the content of selected archive file.

 If archive content is corrupted, error message will be reported.

### cm_OpenArchive

**Shortcut:** `Ctrl+PgDn`

If a directory is selected, will open this directory to show its content.

If a file is selected, ignoring its extension, will try to open it as an archive based on its detected content (see [[Archive Handling#4.12. Configuring the "ID's"|ID configuration]] in other help page).

### cm_ExtractFiles

**Shortcut:** `Alt+F9`

[[Basic Help#^cm_ExtractFiles|Unpack]] one or more selected archives.

| Parameter | Value | Description |
| --- | --- | --- |
| ExtractHere | *(nothing)* | extracted items will be in active panel directory |
| *(nothing, default)* | extracted items will be in inactive panel directory |  |

### cm_OpenVirtualFileSystemList

[[Basic Help#^cm_OpenVirtualFileSystemList|Open VFS list]].

### cm_FileProperties

**Shortcut:** `Alt+Enter`

Show item [[Basic Help#^cm_FileProperties|properties]] (size, data, attributes, etc).

### cm_SetFileProperties

Adjust item properties like creation, modified and last access date, file permission, etc.

### cm_EditComment

**Shortcut:** `Ctrl+Z`

Create or edit [[Basic Help#^cm_EditComment|comment]] for file/directory.

### cm_ContextMenu

**Shortcut:** `Shift+F10`

Shows context menu for files and folders.

 In Windows Double Commander will show the system context menu (as in Windows Explorer), in other operating systems Double Commander creates its own context menu with typical actions.

| Parameter | Value | Description |
| --- | --- | --- |
| justactionmenu | 0/false/off/no | menu will include the default system context menu AND the file extensions associated actions defined in Double Commander (default) |
| 1/true/on/yes | menu will include only the file extensions associated actions defined in Double Commander (the default system context menu won't be displayed) |  |

### cm_Open

**Shortcut:** `Enter`

Open a file or program under cursor.

Associated application based on file association configuration might be used, etc.

### cm_ShellExecute

**Shortcut:** `Ctrl+Alt+Enter`

Will invoke a program for the selected file from the system file associations.

A single parameter may also be provided for the call.

### cm_SymLink

Create [[Basic Help#^cm_SymLink|symlink]] to file/directory.

### cm_HardLink

Create [[Basic Help#^cm_HardLink|hard link]].

### cm_FileSpliter

[[Basic Help#^cm_FileSpliter|Split]] files dialog.

### cm_FileLinker

[[Basic Help#^cm_FileLinker|Combine]] multiple splitted files together to form one single file.

### cm_CheckSumCalc

[[Basic Help#^cm_CheckSumCalc|Calculate]] file checksum (MD5, SHA1, etc).

### cm_CheckSumVerify

[[Basic Help#^cm_CheckSumVerify|Verify]] MD5, SHA1, etc. checksum.

## 2.5. Configuration

Access options and configurations of Double Commander.

### cm_Options

Open [[Basic Help#^cm_Options|configuration]] dialog.

 Command supports a single parameter to jump to a specific configuration section.

 Here is [[cm_Options Reference|a link]] for possible parameters to use.

### cm_ConfigToolbars

Access configuration of the toolbar.

### cm_ConfigDirHotList

**Shortcut:** `Ctrl+Shift+D`

Access configuration of the directory hotlist.

 It is equivalent to cm_WorkWithDirectoryHotlist command with the following parameters:

 action=config source=%Ds

### cm_WorkWithDirectoryHotlist

Access the "Directory Hotlist" configuration window.

With the parameters, you may control which actions will be done regarding the hotlist.

| Parameter | Value | Description |
| --- | --- | --- |
| action | add | add an entry (target will be added depending of option in config) |
| addsrconly | will add an entry with source only |  |
| addboth | will add an entry and target |  |
| config | config an entry |  |
| show | simply show the config window |  |
| addsel | add the current selected directory(ies)<br>(other parameters are ignored) |  |
| directconfig | config the specified "nth" entry |  |
| *(nothing)* | same as "add" |  |
| source | source_path | the directory to add/config as "source" |
| *(nothing)* | directory the active panel is in |  |
| target | target_path | the directory to add/config as "target" |
| *(nothing)* | directory the inactive panel is in |  |
| index | 0-999 | if action=directconfig, the "nth" entry from the hotlist |
| *(nothing)* | index 0 will be used |  |

Example: "cm_WorkWithDirectoryHotlist action=addboth"

This will add to directory hotlist both current directories of active and inactive frame as source and target respectively.

### cm_FileAssoc

Open file associations [[Configuration#^ConfigAssociations|configuration]].

### cm_ConfigFolderTabs

Access configuration for settings related with folder tabs.

### cm_ConfigFavoriteTabs

Access configuration of the Favorite Tabs.

### cm_ConfigTreeViewMenus

Access configuration of the Tree View Menus. This is where we could configure for which command by default we want to use the tree view menu style of selection.

### cm_ConfigTreeViewMenusColors

Access configuration of the color used with the Tree View Menu section interface.

### cm_ConfigSearches

Access configuration of general options regarding file search.

### cm_ConfigHotKeys

Access configuration of hotkeys.

### cm_ConfigSavePos

Will save current state and position of the main window of DC.

### cm_ConfigSaveSettings

Will save all the current settings and history, just like if you would close application and restore.

*This might be useful if you've used DC during a long session and you want to save current context in case system would crash and you do not want to lose current history when you would restart DC.*

### cm_ConfigArchivers

Will launch the configuration page of [[Archive Handling|the external archivers]].

### cm_ConfigTooltips

Will launch the configuration page for the tooltips.

### cm_ConfigPlugins

Access configuration of plugins.

### cm_AddPlugin

This command makes it easy to add plugins, two ways are supported:

 1) Select a plugin file and Double Commander will automatically detect its type (WCX, WDX, WFX, WLX or DSX), open the required settings section and add it to the list.

 2) Select the archive that contains the plugin and a special file `pluginst.inf` (the plugin file and `pluginst.inf` must be located in the root of the archive): the content of the archive will be extracted to the appropriate directory, the plugin will be added to the settings and Double Commander will open the corresponding settings section. If settings are stored in the user profile, Double Commander will use the "plugins" folder in the user's directory:

- Windows XP: *C:\Documents and Settings\<UserName>\Local Settings\doublecmd\plugins*
- Windows Vista/7+: *C:\Users\<UserName>\AppData\Local\doublecmd\plugins*
- Unix-like OS: */home/<UserName>/.local/share/doublecmd/plugins*

In the portable version, Double Commander will use the "plugins" folder in the program directory.



 Note: The first method of adding plugins requires to first place the files in a suitable location, however, in this case, Double Commander will report an error if the plugin could not be loaded (for example, if the operating systems does not contain the necessary libraries).



 Filename can be passed as a parameter.

## 2.6. Network

Related directly with computer network.

### cm_NetworkConnect

[[Basic Help#2.1.4. "Network"|Network connect]].

### cm_NetworkDisconnect

[[Basic Help#2.1.4. "Network"|Network disconnect]].

### cm_CopyNetNamesToClip

Windows only: copy names with UNC path.

## 2.7. Miscellaneous

Inevitable category with commands we did not in which category to place them!
Effort has been made to try to don't place too much commands in this category.

### cm_CalculateSpace

**Shortcut:** `Ctrl+L`

Calculate [[Basic Help#^cm_CalculateSpace|occupied]] space of selected items in active panel.

### cm_Benchmark

Launch a simple benchmark consisting in running supported hash functions.

### cm_RunTerm

**Shortcut:** `F9`

Starts a [[Basic Help#^cm_RunTerm|terminal]].

### cm_ExecuteScript

Execute Lua script file (requires Lua .DLL installed), see details [[Lua Scripting|here]].

| Parameter | Value | Description |
| --- | --- | --- |
| *{first}* | file name | path to Lua script file |
| *{param1}* | command line parameter #1 | passed as command line parameters to Lua script |
| *{param2}* | command line parameter #2 |  |
| *{paramX}* | command line parameter #X |  |

### cm_LoadList

Load list of files/folders from the specified text file (plain text file containing full file names, one per line). Use UTF-8 without BOM.

| Parameter | Value | Description |
| --- | --- | --- |
| filename | file name | full path to file with list |
| side | left | load list into left panel |
| right | load list into right panel |  |
| active | load list into active panel |  |
| inactive | load list into inactive panel |  |
| *(nothing)* | load list into active panel |  |
| *(absent)* | load list into active panel |  |

## 2.8. Mark

Select the items on which the file operations will took place.

### cm_MarkPlus

**Shortcut:** `Num +`

[[Basic Help#^cm_MarkPlus|Select]] items in active panel using a mask (provided or not) according the following parameters:

| Parameter | Value | Description |
| --- | --- | --- |
| mask | *<any string>* | the filter to use |
| *(absent)* | will prompt user to type filter |  |
| casesensitive | 0/false/off/no | filtering will be done ignoring case |
| 1/true/on/yes | filtering will be done case sensitive |  |
| *(absent)* | case sensitivity will be the last one used for the current file view |  |
| ignoreaccents | 0/false/off/no | filtering will be done evaluating an exact match regarding accentuated characters |
| 1/true/on/yes | items and mask will be compared ignoring their accent and ligatures replaced by distinct letters |  |
| *(absent)* | ignoring or not accents will be like the last time it was specified for that file view |  |
| windowsinterpretation | 0/false/off/no | filtering will be done like DC legacy |
| 1/true/on/yes | filtering will be done like Windows |  |
| *(absent)* | using DC legacy filtering or Windows one will be like the last time it was specified for that file view |  |
| attr | d- | filtering will ignore directories and take only files |
| d+ | filtering will ignore files and take only directories |  |
| h- | filtering will ignore hidden files (Windows) |  |
| ux+ | filtering will take only entries with attribute owner's executable (Linux) |  |
| uw+\|gw+\|ow+ | filtering will take files that are writable either by user, group or anybody else (Linux) |  |
| *(absent)* | filtering will be done according to what's configured in "File views", section "Marking/Unmarking entries", the option "Default attribute mask value to use". |  |
|  | note: this means "attr=" with no right value.<br>filter everything, no matter the configured "Default attribute mask" |  |

**Note1:** So if command is used without any parameters, user will be prompt to enter its filter and other options will be the same ones as the last time their were specified in the current session foreach file view.

 **Note2:** When using filtering like Windows as oppose of DC legacy, file with no extension will be selected with filter **.**

 **Note3:** When specifying the "mask" parameter, please note you may also use predefined selection type simply by preceding the name of it with symbol ">" like "*mask=>Pascal files*".

 **Note4:** When using filtering parameter "*ignoreaccents=TRUE*", the ligatured characters like "*œ*" for example will be evaluated as the sequence "*oe*". So for example "*cœur*" will match "*coeur*".

 **Note5:** The fact to use parameters like "casesensitive" for example will not affect the subsequent usage the cm_MarkPlus with no parameters which will use the default same parameters of last time it was prompting the user.

 **Note6:** Regarding the "attr" possible parameter values, see the "[[Find Files#3.1. Searching for files with specific attributes.|Searching for files with specific attributes]]." section in the "Find files" help file. The way to specify the filter regarding the attributes is the same.

 **Example1:** "cm_MarkPlus mask=*.pas;*.dfm;*.dpr;*.inc casesensitive=false" This will select all the files matching the given filter mask (which is basically common Delphi source file extensions) and ignoring the case of the letters.

 **Example2:** "cm_MarkPlus mask=*ecole*.docx ignoreaccents=true" This will select all the files matching the given filter mask (which is basically Microsoft Word document with the word "ecole" in them) ignoring the accents. This means it will select file with "école" and "ecole" in them since accent are ignored.

 **Note7:** If the [[Find Files#3. Tab "Advanced"|duplicate search]] result is open in the active panel, all parameters will be ignored.

### cm_MarkMinus

**Shortcut:** `Num -`

[[Basic Help#^cm_MarkMinus|Unselect]] items in active panel matching the mask (provided or not) according the the same parameters as the [[Internal Commands#cm_MarkPlus]] command.

### cm_MarkMarkAll

**Shortcut:** `Ctrl+A, Ctrl+Num +`

Will basically select [[Basic Help#^cm_MarkMarkAll|all]] the entries in the active panel according to attribute filter that follows.

| Parameter | Value | Description |
| --- | --- | --- |
| attr | d- | filter every entries that are not a directories |
| d+ | filter every entries that are a directories |  |
| h- | filter every entries that don't have the hidden attributes |  |
| ux+ | filter all entries with attribute owner's executable (Linux) |  |
| uw+\|gw+\|ow+ | filter all entries that are writable either by user, group or anybody else (Linux) |  |
| *(absent)* | will select everything that match what's configured in "File views", section "Marking/Unmarking entries", the option "Default attribute mask value to use". |  |
|  | note: this means "attr=" with no right value.<br>filter everything, no matter the configured "Default attribute mask" |  |

### cm_MarkUnmarkAll

**Shortcut:** `Ctrl+Num -`

Will unselect [[Basic Help#^cm_MarkUnmarkAll|all]] the entries of the active panel according to the same filter described in table of [[Internal Commands#cm_MarkMarkAll]] command.

### cm_MarkInvert

**Shortcut:** `Num *`

Will [[Basic Help#^cm_MarkInvert|Invert]] the selected state of all the entries matching the same filter described in table of [[Internal Commands#cm_MarkMarkAll]] command.

### cm_MarkCurrentPath

[[Basic Help#2.1.2. "Mark"|Mark]] files with the same path as item under cursor of active panel.

 **Note:** It might seem useless at first look but may be used in at least two situations:

 After you've filled a panel with search results coming from various level of directories
 After you've invoke the [[Internal Commands#cm_FlatView]] internal command.

### cm_UnmarkCurrentPath

[[Basic Help#2.1.2. "Mark"|Unmark]] files with the same path as item under cursor of active panel.

 See note of [[Internal Commands#cm_MarkCurrentPath]] for the possible usefulness of this command.

### cm_MarkCurrentName

[[Basic Help#2.1.2. "Mark"|Mark]] files with the same filename ignoring the extension as item under cursor of active panel.

### cm_UnmarkCurrentName

[[Basic Help#2.1.2. "Mark"|Unmark]] files with the same filename ignoring the extension as item under cursor of active panel.

### cm_MarkCurrentExtension

**Shortcut:** `Shift+Num +`

[[Basic Help#2.1.2. "Mark"|Mark]] files with the same extension as item under cursor of active panel.

### cm_UnmarkCurrentExtension

**Shortcut:** `Shift+Num -`

[[Basic Help#2.1.2. "Mark"|Unmark]] files with the same extension as item under cursor of active panel.

### cm_MarkCurrentNameExt

[[Basic Help#2.1.2. "Mark"|Mark]] files with the same filename and extension as item under cursor of active panel.

 See note of [[Internal Commands#cm_MarkCurrentPath]] for the possible usefulness of this command.

### cm_UnmarkCurrentNameExt

[[Basic Help#2.1.2. "Mark"|Unmark]] files with the same filename and extension as item under cursor of active panel.

 See note of [[Internal Commands#cm_MarkCurrentPath]] for the possible usefulness of this command.

### cm_CompareDirectories

Will select the items, in both active and inactive panels, that are not present in the opposite panel. Files with the same names will be compared by modification date, after that, newer files will be selected.

| Parameter | Value | Description |
| --- | --- | --- |
| files | on/off | select files |
| directories | on/off | select directories |
| *(nothing, default)* | select files only |  |

### cm_SaveSelection

Used in conjunction with [[Internal Commands#cm_RestoreSelection]].

The cm_SaveSelection command will save in internal buffer current selected items.

Then later, the command [[Internal Commands#cm_RestoreSelection]] could be use to re-select again the same items that were selected before.

### cm_RestoreSelection

See previous [[Internal Commands#cm_SaveSelection]] command.

### cm_SaveSelectionToFile

Save the current selection to a file.

 You may specify the output filename into the first parameter.

 If no parameter is supplied, Double Commander will prompt user to enter one.

### cm_LoadSelectionFromFile

Will read the content of the supplied file to select items from what is read from the file.

 This file could be supplied as the first parameter of the internal command.

 If no file is supplied, application will prompt use to enter one.

### cm_LoadSelectionFromClip

Will select the item of the active panel based on the content of the clipboard.

### cm_SaveFileDetailsToFile

Save all shown columns of selected items to file.

 You may specify the output filename into the first parameter.

 If no parameter is supplied, Double Commander will prompt user to enter one.

## 2.9. Clipboard

Actions related to interact between system's clipboard and selected items.

### cm_CutToClipboard

**Shortcut:** `Ctrl+X`

Cut selected text, file or directory to clipboard.

### cm_CopyToClipboard

**Shortcut:** `Ctrl+C`

Copy selected text, file or directory to clipboard.

### cm_PasteFromClipboard

**Shortcut:** `Ctrl+V`

Paste data from clipboard.

### cm_CopyNamesToClip

**Shortcut:** `Ctrl+Shift+X`

Copy item [[Basic Help#^cm_CopyNamesToClip|names]] to clipboard.

### cm_CopyFullNamesToClip

**Shortcut:** `Ctrl+Shift+C`

Copy item [[Basic Help#^cm_CopyFullNamesToClip|full names]] to clipboard.

 One parameter is available, we can specify the preferred directory separator:

| Parameter | Value | Description |
| --- | --- | --- |
| separator | *directory separator* | use "/" or "\" (without quotes) |
| *(nothing, default)* | use the system value: in Unix/Linux system it will be "/" and in Windows it will be "\" |  |

### cm_CopyPathOfFilesToClip

Will copy the full path of the current selected items including an ending directory separator.

 One parameter is available, we can specify the preferred directory separator, see the description of [[Internal Commands#cm_CopyFullNamesToClip]].

### cm_CopyPathNoSepOfFilesToClip

Will copy the full path of the current selected items excluding an ending directory separator.

 One parameter is available, we can specify the preferred directory separator, see the description of [[Internal Commands#cm_CopyFullNamesToClip]].

### cm_CopyFileDetailsToClip

Will copy file information of selected items onto the clipboard.

## 2.10. Navigation

To go from one folder to another to access various items according to their location.

### cm_DirHistory

**Shortcut:** `Ctrl+H`

Invoke [[Basic Help#^cm_DirHistory|dir history]] menu.

| Parameter | Value | Description |
| --- | --- | --- |
| menutype | popup | directories in history will be displayed in a popup menu |
| treeview | directories in history will be displayed in a tree view menu |  |
| *(nothing)* | the default is assumed to be through a popup menu |  |
| position | panel | menu will be shown from the top left corner of active panel |
| cursor | menu will be shown at the current mouse cursor position |  |
| *(nothing)* | the default is assumed to be from the top left corner of active panel |  |
| *(nothing, default)* | popup menu shown from top left corner of active panel |  |

### cm_DirHotList

**Shortcut:** `Ctrl+D`

Directory [[Basic Help#^cm_DirHotList|hotlist]].

| Parameter | Value | Description |
| --- | --- | --- |
| menutype | popup | hot directories will be displayed in a popup menu |
| treeview | hot directories will be displayed in a tree view menu |  |
| *(nothing)* | the default is assumed to be through a popup menu |  |
| position | panel | menu will be shown from the top left corner of active panel |
| cursor | menu will be shown at the current mouse cursor position |  |
| *(nothing)* | the default is assumed to be from the top left corner of active panel |  |
| *(nothing, default)* | popup menu shown from top left corner of active panel |  |

### cm_SyncChangeDir

Synchronous directory changing in both panels.

 Synchronous navigation is disabled when this command is called again or automatically if there are no matching folder names.

### cm_ChangeDirToParent

**Shortcut:** `Ctrl+PgUp, Backspace`

Go to the parent directory of the current shown one.

### cm_ChangeDirToHome

**Shortcut:** `Ctrl+Shift+Home`

Go to to the user's home directory.

### cm_ChangeDirToRoot

**Shortcut:** `Ctrl+\`

Go to root directory ("/" in Unix and GNU/Linux) or root of the current disk (Windows).

 Also see the description of the `"\"` button [[Basic Help#2.4. Drives list|here]].

### cm_TargetEqualSource

**Shortcut:** `Alt+Z`

Open the directory of the active panel in the opposite panel.

### cm_TransferLeft

**Shortcut:** `Ctrl+ ←`

Open directory under cursor in the left panel.

### cm_TransferRight

**Shortcut:** `Ctrl+ →`

Open directory under cursor in the right panel.

### cm_LeftEqualRight

Show same directory in left panel than what is in the right panel.

### cm_RightEqualLeft

Show same directory in right panel than what is in the left panel.

### cm_Exchange

**Shortcut:** `Ctrl+U`

[[Basic Help#^cm_Exchange|Swap]] file panels.

### cm_QuickSearch

**Shortcut:** `Ctrl+S`

[[Basic Help#^cm_QuickSearch|Quick search]] in directory.

| Parameter | Value | Description |
| --- | --- | --- |
| search | on/off/cycle | Determine the state of the quick search frame at the bottom:<br> - when it's "on", the specified search parameters are applied and quick search frame is shown at the bottom<br> - when it's "off", quick search is removed and search frame is hidden<br> - when it's "cycle", it is to use for when you invoke many time in a row the command to go to the next matching item |
| direction | first/last/next | Determine the direction of the quick search for the item that match the search criterias:<br> - when it's "first", to the first item found from the top<br> - when it's "last", to the last item<br> - when it's "next", to the next one after the current one at the moment of the search. Please note that it may do a wrap around to come back to prior item if none was found after the current selected one.<br> *Note: This option is unrevelant when the "search=cycle". |
| matchbeginning | on/off/toggle | sets or toggles the *match beginning* option |
| matchending | on/off/toggle | sets or toggles the *match ending* option |
| casesensitive | on/off/toggle | sets or toggles case sensitivity |
| files | on/off/toggle | sets or toggles filtering files |
| directories | on/off/toggle | sets or toggles filtering directories |
| filesdirectories | toggles between filtering only files, only directories or both |  |
| text | *<any string>* | sets *any string* as the new searched string |

### cm_QuickFilter

**Shortcut:** `Ctrl+F`

It allows to [[Basic Help#^cm_QuickSearch|filter the file list]] to show only desired files/directories.

| Parameter | Value | Description |
| --- | --- | --- |
| filter | on/off/toggle | - when it's "on", the specified filter is applied and configurable filter frame is shown at the bottom<br> - when it's "off", filtering is removed and filter frame is hidden<br> - when it's "toggle", it will toggle between the two previous states |
| matchbeginning | on/off/toggle | sets or toggles the *match beginning* option |
| matchending | on/off/toggle | sets or toggles the *match ending* option |
| casesensitive | on/off/toggle | sets or toggles case sensitivity |
| files | on/off/toggle | sets or toggles filtering files |
| directories | on/off/toggle | sets or toggles filtering directories |
| filesdirectories | toggles between filtering only files, only directories or both |  |
| text | *<any string>* | sets *any string* as the new filter |

For example, setting a tool button with the following parameters will allow pressing button to toggle the application of a filter to show only the "txt" file or not each time the button is pressed:

 text=txt
 filter=toggle
 files=on
 directories=on
 matchbeginning=off
 matchending=on

 When no parameter at all is specified, it will be assumed to activate the filter AND the other options will be the same as previous filter **except** for the text with the focus ready in the text box to allow you to type the desired text to set filter.

### cm_EditPath

User may type directly the directory he wants see in the selected panel. Also see `F2` and `Shift+F6` [[Keyboard Layout#2. Main window|here]].

### cm_ChangeDir

Will switch the active/inactive/left/right panel to the specified directory(ies).

 Please note that you may specify more than one parameter, so with only one command, you may set both source and target path.

| Parameter | Value | Description |
| --- | --- | --- |
| activepath | *specified_path* | will switch the active panel to the *specified_path* |
| inactivepath | *specified_path* | will switch the inactive panel to the *specified_path* |
| leftpath | *specified_path* | will switch the left panel to the *specified_path* |
| rightpath | *specified_path* | will switch the right panel to the *specified_path* |
| For legacy backward compatibility, you may also provide simply a single path as single parameter and DC will switch active panel to that path. |  |  |

Examples:

 *cm_ChangeDir activepath=%$DESKTOP% inactivepath=E:\Medias\Paul Houde*

 This will make the active panel to show content of the current user's desktop folder and in the inactive panel you'll see the content of "Paul Houde" one.

 *cm_ChangeDir leftpath=C:\Working rightpath=E:\Euler*

 No matter where is the current active panel, the left one will show content of "Working" folder and the right panel will show the one of "Euler".

 *cm_ChangeDir \\TERA-06\OPENSHARE1\MEDIAS\PICTURES\2015*

 The active panel will switch to show content of the network mentioned path.

 *cm_ChangeDir wfx://FTP*

 The mentioned WFX plugin will be opened in the active panel.

### cm_GoToFirstEntry

Place cursor on first folder or file in list.

### cm_GoToLastEntry

Place cursor on last folder or file in list.

### cm_GoToNextEntry

Place cursor on next folder or file.

### cm_GoToPrevEntry

Place cursor on previous folder or file.

### cm_GoToFirstFile

Place cursor on first file in list.

### cm_GoToLastFile

Place cursor on last file in list.

### cm_ViewHistory

Will popup at the cursor position, the last directories visited.

| Parameter | Value | Description |
| --- | --- | --- |
| menutype | popup | directories in history will be displayed in a popup menu |
| treeview | directories in history will be displayed in a tree view menu |  |
| *(nothing)* | the default is assumed to be through a popup menu |  |
| position | panel | menu will be shown from the top left corner of active panel |
| cursor | menu will be shown at the current mouse cursor position |  |
| *(nothing)* | the default is assumed to be from the mouse cursor position |  |
| *(nothing, default)* | popup menu shown at the current mouse cursor position |  |

### cm_ViewHistoryNext

**Shortcut:** `Alt+ →`

According to list of last directories visited, will set the active panel to the very next one, if any, visited prior to current one.

### cm_ViewHistoryPrev

**Shortcut:** `Alt+ ←`

According to list of last directories visited, will set the active panel to the very last one visited prior to current one.

### cm_OpenDriveByIndex

In the current tab of the specified panel, will show content of the specified drive.

If no panel is specified, it will be in the current active panel.

| Parameter | Value | Description |
| --- | --- | --- |
| index | 1 | will use **1**st drive of list |
| 2 | will use **2**nd drive of list |  |
| 3 | will use **3**rd drive of list |  |
| *n* | will use ***n***th drive of list |  |
| side | left | selected drive will be in **left panel** |
| right | selected drive will be in **right panel** |  |
| inactive | selected drive will be in **inactive panel** |  |
| *(absent)* | selected drive will be in **current active panel** |  |
| *(nothing)* | Specifying at least the **index** is mandatory. |  |

Example: "cm_OpenDriveByIndex side=left index=2" will focus panel on left and show drive E: content assuming in our current drive list we have C:, E:, S: and X:.

### cm_FocusSwap

Switch focus between left and right panel.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | will set focus on left panel |
| right | will set focus on right panel |  |
| *(nothing, default)* | will set focus on the opposite panel of the current selected one |  |

## 2.11. Help

Access the integrated help files of Double Commander.

### cm_HelpIndex

**Shortcut:** `F1`

Open Double Commander [[Indice|help]] index page.

### cm_Keyboard

Open the [[Keyboard Layout|help page]] with the default keyboard shortcuts of Double Commander.

### cm_VisitHomePage

Go to Double Commander's home page.

### cm_About

Show program "About" information.

## 2.12. Window

Commands related with the Double Commander window, its look and behavior, like any other computer application.

### cm_HorizontalFilePanels

**Shortcut:** `Ctrl+Shift+H`

Will set the arrangement of panels between two vertical ones disposed in left/right OR two horizontal ones disposed in top/bottom.

| Parameter | Value | Description |
| --- | --- | --- |
| mode | *(nothing)*/<br>legacy | toggle between vertical/horizontal |
| vertical | vertical panels (default) |  |
| horizontal | horizontal panels |  |

Example: "cm_HorizontalFilePanels mode=horizontal" will force the two panels to be in horizontal disposition, one above the other.

### cm_PanelsSplitterPerPos

Set the panels width, e.g. 50% – equal size.

| Parameter | Value | Description |
| --- | --- | --- |
| splitpct | 0-100 | percentage of whole width to assign to left panel<br>(or top panel if horizontal mode is enabled) |
| *(nothing, default)* | percentage set to 50-50 |  |

Example: "cm_PanelsSplitterPerPos splitpct=80", with vertical panels, will set the left panel width to 80% of the available space.

### cm_ShowMainMenu

Determine if we see the main bar menu or not.

| Parameter | Value | Description |
| --- | --- | --- |
| menu | 1/true/on/yes | main menu is displayed |
| 0/false/off/no | main menu is **not** displayed |  |
| treeview | 1/true/on/yes | on request, the main menu item will be shown under the form of a tree view menu |
| 0/false/off/no | dummy, will simply be ignored |  |
| *(nothing, default)* | toggle the visibility of the main menu |  |

Example: "cm_ShowMainMenu menu=off", will hide the main menu.

### cm_ShowButtonMenu

Determine if we see the toolbar or not.

| Parameter | Value | Description |
| --- | --- | --- |
| toolbar | 1/true/on/yes | toolbar is displayed |
| 0/false/off/no | toolbar is **not** displayed |  |
| treeview | 1/true/on/yes | on request, the toolbar menu item will be shown under the form of a tree view menu |
| 0/false/off/no | dummy, will simply be ignored |  |
| *(nothing, default)* | toggle the visibility of the toolbar |  |

### cm_OperationsViewer

**Shortcut:** `Alt+V`

Shows a window with the file operations process currently in progress if any.

### cm_OpenBar

Ex-command not implemented anymore.

Since the configuration of the toolbar is done via one single simple versatile dedicated configuration window, you may want to refer to [[Internal Commands#cm_ConfigToolbars]] command instead.

### cm_Minimize

Minimize the Double Commander window.

### cm_Exit

**Shortcut:** `Alt+X`

Close Double Commander.

### cm_TreeView

**Shortcut:** `Ctrl+Shift+F8`

Tree View Panel.

### cm_FocusTreeView

**Shortcut:** `Shift+Tab`

Switch focus between current file list and tree view (if enabled).

## 2.13. Command Line

Interact with command line to view past commands and help to invoke new ones.

### cm_FocusCmdLine

**Shortcut:** `Shift+F2`

Change focus to the command line.

### cm_ShowCmdLineHistory

**Shortcut:** `Alt+F8, Ctrl+ ↓`

Show history of all commands used in the [[Basic Help#2.10. Command line|command line]].

| Parameter | Value | Description |
| --- | --- | --- |
| menutype | combobox | the combo box of the command line will be expanded so you may chose the command from the command line history |
| treeview | a tree view menu will be opened above the combox box of the command line |  |
| *(nothing)* | the default is assumed to be through the combo box |  |

### cm_CmdLineNext

Will activate in the next command line typed prior the current one, if any.

### cm_CmdLinePrev

Will activate in the next command line typed after the current one, if any.

### cm_AddPathToCmdLine

**Shortcut:** `Ctrl+P`

Place current path in command line.

| Parameter | Value | Description |
| --- | --- | --- |
| mode | smartquote | will place the added text between quotes, only if necessary (like for example if there are spaces in it and will let it intact if there is no spaces |
| forcequote | will systematically quote that will be added |  |
| neverquote | will systematically never quote that will be added |  |
| prompt | will prompt the user if he wants to quote his added text or not, with the default choice set like if it would be a "mode=smartquote" |  |
| *(nothing)* | the default is assumed to be "mode=smartquote" |  |

### cm_AddFilenameToCmdLine

**Shortcut:** `Ctrl+Enter`

Place filename of current selected item in command line.

**Note:** Command also accepts the same parameters as the [[Internal Commands#cm_AddPathToCmdLine]].

### cm_AddPathAndFilenameToCmdLine

**Shortcut:** `Ctrl+Shift+Enter`

Place current path and filename of selected item in command line.

**Note:** Command also accepts the same parameters as the [[Internal Commands#cm_AddPathToCmdLine]].

### cm_ToggleFullscreenConsole

**Shortcut:** `Ctrl+O`

Toggle fullscreen mode console window.

## 2.14. Tools

For action requiring more than a click.
These action will generally show another window to have Double Commander do some more complex jobs.

### cm_MultiRename

**Shortcut:** `Ctrl+M`

Open [[Multi-Rename Tool]].

| Parameter | Value | Description |
| --- | --- | --- |
| preset | a preset name | The provided preset name will be loaded |
| *(nothing, default)* | Load the last settings used or what has been configured for [[Multi-Rename Tool#10.3. Preset at launch\|Preset at launch]] |  |

### cm_Search

**Shortcut:** `Alt+F7`

Open [[Basic Help#^cm_Search|Search]] dialog with default parameters or with saved template from option "Default search template" (see File Operations > File search).

Also command supports a single parameter to open Search dialog with saved template, use template name as is without quotes.

### cm_AddNewSearch

**Shortcut:** `Ctrl+Shift+F7`

Create and open a new instance of [[Basic Help#^cm_Search|Search]] dialog window. Invoking this command to do a search will preserve the searches we've made earlier in the session. It will also allow to launch a new search instance to search something else while a long search is in progress.

### cm_ViewSearches

If we've launched a few instances of search with the [[Internal Commands#cm_AddNewSearch]], this command will allow us to view a summary of them and be able to switch back to one of them.

### cm_DeleteSearches

If we've launched a few instances of search with the [[Internal Commands#cm_AddNewSearch]], this command will allow us to close and remove from memory all of them at once.

### cm_SyncDirs

Will invoke the [[Synchronize Directories|directory synchronization tool]] to scan left and right panel folder to eventually see the content difference and make them equal.

### cm_CompareContents

Open [[Basic Help#^cm_CompareContents|compare by contents]] dialog.

 If an external diff program is used, the "dir" parameter (without quotes) is available: in this case, the current directories of the left and right file panels will be passed to the program.

### cm_DebugShowCommandParameters

Will simply show a message with the info passed as parameters.

This may be helpful to validate the parameter you're passing to a command.

### cm_DoAnyCmCommand

**Shortcut:** `Shift+F12`

Will show an internal command selector window where user may select any of the possible internal command and execute it.

## 2.15. View

Commands related with the visibility or not of files like the system files, etc.

### cm_Refresh

**Shortcut:** `Ctrl+R`

[[Basic Help#^cm_Refresh|Refresh]] panel.

### cm_ShowSysFiles

**Shortcut:** `Ctrl+.`

Show hidden and system [[Basic Help#^cm_ShowSysFiles|files]].

### cm_SwitchIgnoreList

Enable or not the "[[Configuration#^ConfigIgnore|Ignore list]]" depending of the parameter.

| Parameter | Value | Description |
| --- | --- | --- |
| ignorelist | 1/true/on/yes | ignore list is enabled |
| 0/false/off/no | ignore list is **not** enabled |  |
| *(nothing, default)* | toggle the state of the ignore list |  |

Example: "cm_SwitchIgnoreList ignorelist=on", ignore list is enabled so item present in the ignore list won't be shown in the panels.

## 2.16. Tabs

Interact with tabs by creating new ones, navigate through them, etc.

### cm_NewTab

**Shortcut:** `Ctrl+T`

Create a [[Basic Help#^cm_NewTab|new tab]] for opened directory.

### cm_OpenDirInNewTab

**Shortcut:** `Ctrl+ ↑`

Open directory under cursor at [[Basic Help#^cm_OpenDirInNewTab|new tab]], but don't switch to it.

### cm_NextTab

**Shortcut:** `Ctrl+Tab`

Change to [[Basic Help#^cm_NextTab|next tab]].

### cm_PrevTab

**Shortcut:** `Ctrl+Shift+Tab`

Change to [[Basic Help#^cm_PrevTab|previous tab]].

### cm_MoveTabLeft

Move current tab to the left.

### cm_MoveTabRight

Move current tab to the right.

### cm_RenameTab

Prompt user to rename current tab of active panel.

### cm_CloseTab

**Shortcut:** `Ctrl+W`

Close current tab of active panel.

### cm_CloseAllTabs

Close all tabs of panel(s), excluding the active one, according to following parameters:

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | action closes tabs in **left panel** |
| right | action closes tabs in **right panel** |  |
| active | action closes tabs in **active panel** |  |
| inactive | action closes tabs in **inactive panel** |  |
| both | action closes tabs in **both panels** |  |
| dolocked | 1/true/on/yes | action closes also the **locked tabs** |
| 0/false/off/no | ignore **locked tabs** |  |
| confirmlocked | 1/true/on/yes | if "dolocked" is true, user has to confirm closing locked tabs no matter the configured option "Confirm close locked tabs" |
| 0/false/off/no | if "dolocked" is true, close locked tabs without asking confirmation no matter the configured option "Confirm close locked tabs" |  |
| *(not specified)* | if "dolocked" is true, ask or not user to confirm closing locked tabs according to the configured option "Confirm close locked tabs" |  |
| *(nothing, default)* | close all the non locked tabs, excluding the active tab, on the active panel |  |
| For legacy backward compatibility, you may also provide simply a single word as single parameter like "LeftTabs" and "RightTabs" to specify the panel where to apply command. |  |  |

### cm_CloseDuplicateTabs

Close tabs pointing to same dirs so at the end of action, only one tab for each dir is kept ([[Basic Help#^cm_CloseDuplicateTabs|priority rules]]).

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | action closes duplicated tabs in **left panel** |
| right | action closes duplicated tabs in **right panel** |  |
| active | action closes duplicated tabs in **active panel** |  |
| inactive | action closes duplicated tabs in **inactive panel** |  |
| both | action closes duplicated tabs in **both panels** |  |
| dolocked | 1/true/on/yes | action closes also duplicated **locked tabs** |
| 0/false/off/no | ignore duplicated **locked tabs** |  |
| confirmlocked | 1/true/on/yes | if "dolocked" is true, user has to confirm closing duplicated locked tabs no matter the configured option "Confirm close locked tabs" |
| 0/false/off/no | if "dolocked" is true, close duplicated locked tabs without asking confirmation no matter the configured option "Confirm close locked tabs" |  |
| *(not specified)* | if "dolocked" is true, ask or not user to confirm closing duplicated locked tabs according to the configured option "Confirm close locked tabs" |  |
| *(nothing, default)* | close all the duplicated non locked tabs on the active panel |  |

### cm_CopyAllTabsToOpposite

All tabs from the specified side will be added also on the opposite side. By default with no parameter, it copies tab from the active panel to the inactive panel.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | will copy tabs from **left panel** to the right one |
| right | will copy tabs from **right panel** to the left one |  |
| active | will copy tabs from **active panel** to the inactive one |  |
| inactive | will copy tabs from **inactive panel** to the active one |  |
| both | will copy tabs from **both panel** to the opposite ones |  |
| *(nothing, default)* | will copy tabs from **active panel** to the inactive one |  |

### cm_LoadTabs

Open a file expected to contains tab names and their associated directories to apply to panel.

| Parameter | Value | Description |
| --- | --- | --- |
| filename | *filename.tab* | the file used to load the tabs |
| *(not specified)* | a file requested will appear to prompt the user to indicate from which .tab file to load the tabs from |  |
| loadleftto | left | tabs saved in left panel in .tab file will be in **left** panel |
| right | tabs saved in left panel in .tab file will be in **right** panel |  |
| active | tabs saved in left panel in .tab file will be in **active** panel |  |
| inactive | tabs saved in left panel in .tab file will be in **inactive** panel |  |
| both | tabs saved in left panel in .tab file will be in **both** panels |  |
| none | tabs saved in left panel in .tab file will be **ignored** |  |
| loadrightto | left | tabs saved in right panel in .tab file will be in **left** panel |
| right | tabs saved in right panel in .tab file will be in **right** panel |  |
| active | tabs saved in right panel in .tab file will be in **active** panel |  |
| inactive | tabs saved in right panel in .tab file will be in **inactive** panel |  |
| both | tabs saved in right panel in .tab file will be in **both** panels |  |
| none | tabs saved in right panel in .tab file will be **ignored** |  |
| keep | left | tabs present in **left** panel will be preserved |
| right | tabs present in **right** panel will be preserved |  |
| active | tabs present in **active** panel will be preserved |  |
| inactive | tabs present in **inactive** panel will be preserved |  |
| both | tabs present in **both** panels will be preserved |  |
| none | **none** of the present tabs will be preserved |  |
| For legacy backward compatibility, you may also provide simply a single filename as single parameter and DC will load that .tab file "as is", so left and right tabs will be restored to left and right panel respectively. |  |  |

### cm_SaveTabs

Will save into a file the current tab names and their associated directories, for both left and right, to a .tab file to be eventually loaded back with previous described command.

| Parameter | Value | Description |
| --- | --- | --- |
| filename | *filename.tab* | the file used to save the tabs |
| *(not specified)* | a file requested will appear to prompt the user to indicate to which .tab file to save the tabs to |  |
| savedirhistory | 1/true/on/yes | will save also the history of last directories for each tabs |
| 0/false/off/no | history of last directories won't be saved |  |
| For legacy backward compatibility, you may also provide simply a single filename as single parameter and DC will save to that .tab file. |  |  |

### cm_SetTabOptionNormal

Current tab status to normal.

### cm_SetTabOptionPathLocked

Current tab to "locked", user cannot change directory.

### cm_SetTabOptionPathResets

Current tab to "locked with dir change allowed", user may change directory inside the panel, but if user changes tab and then come back to that one, it will come back to original directory where it was "locked with dir changed allowed".

### cm_SetTabOptionDirsInNewTab

Current tab to "locked with dir change in new tab", user may change directory inside the panel, but as user enters in new directory, that one will be opened in a new tab.

### cm_SetAllTabsOptionNormal

Set back to "normal" all the tabs.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | affects tabs in **left panel** |
| right | affects tabs in **right panel** |  |
| active | affects tabs in **active panel** |  |
| inactive | affects tabs in **inactive panel** |  |
| both | affects tabs in **both panels** |  |
| *(nothing, default)* | affects only the tabs of the active panel |  |

### cm_SetAllTabsOptionPathLocked

All tabs to "locked", user cannot change directory.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | affects tabs in **left panel** |
| right | affects tabs in **right panel** |  |
| active | affects tabs in **active panel** |  |
| inactive | affects tabs in **inactive panel** |  |
| both | affects tabs in **both panels** |  |
| *(nothing, default)* | affects only the tabs of the active panel |  |

### cm_SetAllTabsOptionPathResets

All tabs to "locked with dir change allowed", user may change directory inside the panel, but if user changes tab and then come back to that one, it will come back to original directory where it was locked.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | affects tabs in **left panel** |
| right | affects tabs in **right panel** |  |
| active | affects tabs in **active panel** |  |
| inactive | affects tabs in **inactive panel** |  |
| both | affects tabs in **both panels** |  |
| *(nothing, default)* | affects only the tabs of the active panel |  |

### cm_SetAllTabsOptionDirsInNewTab

All tabs to "locked with dir change in new tab", user may change directory inside the panel, but as user enters in new directory, that one will be opened in a new tab.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | affects tabs in **left panel** |
| right | affects tabs in **right panel** |  |
| active | affects tabs in **active panel** |  |
| inactive | affects tabs in **inactive panel** |  |
| both | affects tabs in **both panels** |  |
| *(nothing, default)* | affects only the tabs of the active panel |  |

### cm_LoadFavoriteTabs

Prompt the user with a menu asking to select a previously saved setup.

| Parameter | Value | Description |
| --- | --- | --- |
| setup | *name* | will load the setup *name* |
| *(nothing)* | no change current tabs, but will unselect current setup selection if any |  |
| menutype | popup | favorite tabs will be displayed in a popup menu |
| treeview | favorite tabs will be displayed in a tree view menu |  |
| *(nothing)* | the default is assumed to be through a popup menu |  |
| position | panel | menu will be shown from the top left corner of active panel |
| cursor | menu will be shown at the current mouse cursor position |  |
| *(nothing)* | the default is assumed to be from the top left corner of active panel |  |
| *(nothing, default)* | popup menu shown from top left corner of active panel |  |

### cm_SaveFavoriteTabs

Will save in the "Favorite Tabs" the current opened tabs. Later on, on request, user may reload these saved setup using the [[Internal Commands#cm_LoadFavoriteTabs]] command.

### cm_ReloadFavoriteTabs

Reload again the last Favorite Tabs setup that was loaded. So if after browsing in every tab and additional tabs were added, etc. we want to restore "as-is" what has been set for the last Favorite Tabs that was loaded, that's the command to invoke.

### cm_ResaveFavoriteTabs

Will resave the current tabs configuration over the last loaded Favorites Tabs entry. This is useful if you realized you're missing a tab in one of your configuration. After loading your Favorite Tabs you add the missing tab you wanted and then you invoke this internal command.

### cm_PreviousFavoriteTabs

Will load the Favorite Tabs setup that is just before in our list the last one we loaded.

### cm_NextFavoriteTabs

Will load the Favorite Tabs setup that is just after in our list the last one we loaded.

### cm_ActivateTabByIndex

Will activate the specified tab in the specified panel where it will also switch to.

If no panel is specified, tabs used will be from the active panel.

| Parameter | Value | Description |
| --- | --- | --- |
| index | 1 | will activate **1**st tab |
| 2 | will activate **2**nd tab |  |
| 3 | will activate **3**rd tab |  |
| *n* | will active ***n***th tab |  |
| -1 | will activate **last** tab |  |
| side | left | will switch to and use tabs of **left panel** |
| right | will switch to and use tabs of **right panel** |  |
| inactive | will switch to and use tabs of **inactive panel** |  |
| *(absent)* | activated tab will be on **current active panel** |  |
| *(nothing)* | Specifying at least the **index** is mandatory. |  |

Example: "cm_ActivateTabByIndex side=right index=1" will activate the 1st tab in the rigth panel and will switch focus on it.

### cm_ShowTabsList

**Shortcut:** `Ctrl+Shift+A`

Show a menu with a list of all open tabs.

| Parameter | Value | Description |
| --- | --- | --- |
| side | left | tabs of the left panel |
| right | tabs of the right panel |  |
| inactive | tabs of the inactive panel |  |
| *(absent)* | tabs of the active panel |  |
| *(nothing, default)* | tabs of the active panel |  |

## 2.17. Logs

Actions related with DC logs file.

### cm_ViewLogFile

Open the current log file of operation.

### cm_ClearLogFile

Will erase the current log file of operation.

### cm_ClearLogWindow

Will clear the log window content.

Originally created by Rustem (dok_rust@bk.ru)

---

[[Indice|← Index]]
