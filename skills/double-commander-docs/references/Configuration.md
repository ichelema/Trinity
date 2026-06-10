---
title: 2.2. Configuration
source: configuration.html
tags: [doublecmd, documentation]
---

# Configuration

## Content

- 1. [[Configuration#1. Configuration files|Configuration files]]
- 2. [[Configuration#2. Configuration|Configuration]]:
  - 2.1. [[Configuration#^ConfigLang|Language]]
  - 2.2. [[Configuration#^ConfigBehaviors|Behaviors]]
  - 2.3. [[Configuration#^ConfigTools|Tools]]
    - 2.3.1. [[Configuration#^ConfigToolsViewer|Viewer]]
    - 2.3.2. [[Configuration#^ConfigToolsEditor|Editor]]
      - 2.3.2.1. [[Configuration#^ConfigToolsEditorHL|Highlighters]]
    - 2.3.3. [[Configuration#^ConfigToolsDiffer|Differ]]
    - 2.3.4. [[Configuration#^ConfigToolsTerminal|Terminal]]
  - 2.4. [[Configuration#^ConfigFonts|Fonts]]
  - 2.5. [[Configuration#^ConfigColor|Colors]]
    - 2.5.1. [[Configuration#^ConfigColorPanels|File panels]]
    - 2.5.2. [[Configuration#^ConfigColorFiles|File types]]
  - 2.6. [[Configuration#^ConfigKeys|Keys]]
    - 2.6.1. [[Configuration#^ConfigHotKeys|Hot Keys]]
  - 2.7. [[Configuration#^ConfigMouse|Mouse]]
    - 2.7.1. [[Configuration#^ConfigMouseDD|Drag & drop]]
  - 2.8. [[Configuration#^ConfigView|Files views]]
    - 2.8.1. [[Configuration#^ConfigViewEx|Files views extra]]
    - 2.8.2. [[Configuration#^ConfigViewBrief|Brief]]
    - 2.8.3. [[Configuration#^ConfigViewFull|Columns]]
      - 2.8.3.1. [[Configuration#^ConfigColumns|Custom columns]]
  - 2.9. [[Configuration#^ConfigPlugins|Plugins]]
  - 2.10. [[Configuration#^ConfigLayout|Layout]]
    - 2.10.1. [[Configuration#^ConfigDrivesList|Drives list button]]
    - 2.10.2. [[Configuration#^ConfigTreeMenu|Tree View Menu]]
    - 2.10.3. [[Configuration#^ConfigTreeMenuColor|Tree View Menu Colors]]
  - 2.11. [[Configuration#^ConfigToolbar|Toolbar]]
    - 2.11.1. [[Configuration#^ConfigToolbar|Toolbar Middle]]
    - 2.11.2. [[Configuration#^ConfigToolbarEx|Toolbar Extra]]
  - 2.12. [[Configuration#^ConfigOperations|File operations]]
    - 2.12.1. [[Configuration#^ConfigSearch|File search]]
    - 2.12.2. [[Configuration#^ConfigRename|Multi-Rename]]
  - 2.13. [[Configuration#^ConfigTabs|Folder tabs]]
    - 2.13.1. [[Configuration#^ConfigFavoriteTabs|Favorite Tabs]]
    - 2.13.2. [[Configuration#^ConfigTabsEx|Folder tabs extra]]
  - 2.14. [[Configuration#^ConfigLog|Log]]
  - 2.15. [[Configuration#^ConfigDC|Configuration]]
  - 2.16. [[Configuration#^ConfigQuick|Quick search/filter]]
  - 2.17. [[Configuration#^ConfigMisc|Miscellaneous]]
  - 2.18. [[Configuration#^ConfigRefresh|Auto refresh]]
  - 2.19. [[Configuration#^ConfigIcons|Icons]]
  - 2.20. [[Configuration#^ConfigIgnore|Ignore list]]
  - 2.21. [[Configuration#^ConfigArchivers|Archivers]]
  - 2.22. [[Configuration#^ConfigTooltips|Tooltips]]
  - 2.23. [[Configuration#^ConfigAssociations|File associations]]
    - 2.23.1. [[Configuration#^ConfigAssocEx|File associations extra]]
  - 2.24. [[Configuration#^ConfigDirHotlist|Directory Hotlist]]
    - 2.24.1. [[Configuration#^ConfigDirHotlistEx|Directory Hotlist Extra]]

## 1. Configuration files

Double Commander keeps its configuration settings in files. You may configure the location of these configuration file from the [[Configuration#^ConfigDC|Configuration]] settings section. There is usually no need to edit these files manually, since with rare exceptions, the parameters of Double Commander are available through the program's interface.

The main files are:

- `doublecmd.xml` – all the main program settings;
- `doublecmd.cfg` – settings that are applied before initialization of all program components and loading `doublecmd.xml`;
- `colors.json` – all color settings, Double Commander stores color values in the "Light" and "Dark" profiles and selects the profile automatically depending on the current theme (light or dark theme);
- `extassoc.xml` – file extension association configuration;
- `favoritetabs.xml` – favorite tabs;
- `history.xml` – command line and directory history, search and replace, etc.;
- `multiarc.ini` – external archivers;
- `pixmaps.txt` – maps file extensions to MIME-types icon names;
- `session.ini` – size, position and state of child program windows (these settings are saved separately for each screen resolution);
- `shortcuts.scf` – keyboard layout settings;
- `tabs.xml` – list of opened tabs;
- few others... – etc...

The files are generated automatically, except for `multiarc.ini` and `pixmaps.txt`: they are included in the distribution of Double Commander (in the "default" folder) and are copied to the directory of configuration files when the program is first launched.

The configuration version in `doublecmd.xml` defines the data storage format: if it has changed in the new version of the program (for example, new parameters have been added or existing ones have changed), then at the first start Double Commander will update the configuration files. The upgrade process will back up the previous version of `doublecmd.xml`.

## 2. Configuration

The "Options" window allows to set almost all of the options in Double Commander, but there are [[doublecmd.xml Settings|several parameters]] that can only be changed manually in the `doublecmd.xml` configuration file.

A filter by parameter name is available at the bottom of the window: the program will display only those sections that contain a matching parameter. To open the corresponding section in the program help, you can use the *Help* button or the `F1` key.

Double Commander has several [[Internal Commands#2.5. Configuration|internal commands]] to open the configuration dialog and quickly jump to the desired section.

Double Commander supports importing/exporting some settings: directory hotlist, favorite tabs, external archivers, toolbar (main and middle), tooltips. Also, the list of hotkeys can be saved to a new file and you can switch between them.

Note: To the right of the file or directory choose buttons is the button *Some functions to select appropriate path* ![[bhelper.png|Some functions to select appropriate path]]: the popup menu contains lists of variables (including environment variables) and some additional functions, see description [[Directory Hotlist#2.9. Helper with path and target definition|here]].

**2.1. Language** ^ConfigLang

These are the various translations available for Double Commander. You can choose your preferred language.

**2.2. Behaviors** ^ConfigBehaviors

There are several parameters that affect certain behaviors of Double Commander.

![[pic58.png|Behaviors]]

*Allow only one copy of DC at a time* – If enabled, only one copy of the program can be run. If you try to run a second copy of Double Commander, the first copy will be activated.

*Move icon to system tray when minimized* – When minimized Double Commander will display its icon in the system tray (notification area) rather than the panel (or Windows taskbar).

*Always show tray icon* – If enabled, in addition to the Double Commander window button on the panel (or Windows taskbar), it will additionally show the tray icon.

*Drives blacklist* – use this to hide certain drives in the drives panel menu bar. Each item must contain the full path to the drive/mount point. Separate multiple drives with semicolons ";" without spaces. Examples: `/media/cdrom;/mnt/win_c` (Linux) or `a:\;b:\;d:\` (Windows). Also in Unix/Linux you may use wildcard mask, example for AppImage files: `/tmp/.mount_*`. Hidden drives will still be available, for example, you can open them from the Directory Hotlist menu or change the path manually.

*Automatically hide unmounted devices* – An unmounted device will be automatically removed from the [[Basic Help#2.3. Drives button bar|drive button bar]] and from the [[Basic Help#2.4. Drives list|drives list]].

**2.3. Tools** ^ConfigTools

This section contains the settings of the built-in Double Commander tools (editor (`F4`), viewer (`F3`) and file comparison tool) and commands for launching the terminal.

You can specify external programs for edit, view and find differences. These external programs will be used instead of the internal tools.

**2.3.1. Tools > Viewer** ^ConfigToolsViewer

There are two groups of parameters in this section:

![[pic50.png|Viewer]]

The first group allows you to specify an external program for viewing files. Double Commander will automatically add the full filename as the last launch parameter each time the viewer is called.

Additionally: *Execute in terminal* and *Keep terminal window open after executing program* can be useful if you are using a console program and/or if the program's terminal output is important (or just temporarily for debugging).

The next group of parameters is *Internal viewer options*, however almost all parameters and switches are available in the window of [[File Viewer|built-in viewer]].

*Number of columns in book viewer* – see description of this mode [[File Viewer#2.3. "View"|here]].

There are also [[doublecmd.xml Settings|several parameters]] available that can only be changed manually in the `doublecmd.xml` configuration file.

**2.3.2. Tools > Editor** ^ConfigToolsEditor

![[pic51.png|Editor]]

The first group of parameters allows you to specify an external program for editing text files. Double Commander will automatically add the full filename as the last launch parameter each time the editor is called.

Additionally: *Execute in terminal* and *Keep terminal window open after executing program* can be useful if you are using a console program and/or if the program's terminal output is important (or just temporarily for debugging).

Internal editor options:

*Auto Indent* – Allows to indent the caret, when new line is created with `Enter`, with the same amount of leading white space as the preceding line.

*Delete trailing spaces* – Auto delete trailing spaces, this applies only to edited lines.

*Caret past end of line* – Allows caret to go into empty space beyond end-of-line position.

*Show special characters* – Shows special characters for spaces and tabulations.

*Use spaces instead tab characters* – Converts tab characters to a specified number of space characters (when entering).

*Tab indents blocks* – If enabled, `Tab` and `Shift+Tab` act as block indent, unindent when text is selected.

*Smart Tabs* – When the `Tab` key is used, caret will go to the next non-space character of the previous line.

*Group Undo* – If enabled, all continuous changes of the same type will be processed in one call to the undo or redo command, instead of undoing/redoing each individual text change.

*Tab width* – The width of the tab character (in number of characters). If *Use spaces instead tab characters* is enabled, then the `Tab` key will insert the specified number of space characters. This setting does not apply if the *Smart Tabs* option is enable.

*Block indent* – sets the number of characters by which the indent will increase or decrease when using the corresponding commands.

*Right margin* – Line length marker, thin vertical line at the given position: lines will not be truncated with a forced line break, it is just a visual hint. Useful in cases where there is a recommendation to limit the length of strings (for example, 80 or 120 characters).

**2.3.2.1. Tools > Editor > Highlighters** ^ConfigToolsEditorHL

The SynEdit component is used for the built-in editor, some settings of syntax highlighting rules that are part of SynEdit are available in this section.

![[pic52.png|Syntax highlighting]]

At the top of the window there is a drop-down menu with file types (plain text, programming and markup languages) and a field for the list of file extensions. Buttons:

- *Save* – will save the changes in the list of file extensions.
- *Reset* – will reset the list to the default value.

In the left part of the window there is a list of available elements for the selected file type, in the right part there is a preview area.

You can change the text and background colors and font style (underline, bold, italic and strike out) used for keywords, strings, numbers, operators, and so on. For the default text, only the text and background colors are available.

*Text-mark* is used to add a border around the element: you can choose the color, the type of border and the type of line.

*Use (and edit) global scheme settings* and *Use local scheme settings* are for default text only: you can change the colors for all file types at once, or only for some.

All settings are saved in the `colors.json` file.

Note: Possible ways to change (fix or improve) parsing of files (syntactic analysis), keyword lists, and so on:

- suggest changes to the Lazarus project (the best way);
- independently make changes to the source code of the SynEdit component and compile Double Commander.

In addition, Double Commander also uses the SynUniHighlighter component for syntax highlighting, see the [[FAQ#^f4_syntax|FAQ]] for details.

**2.3.3. Tools > Differ** ^ConfigToolsDiffer

Almost all parameters and switches are available in the window of built-in differ, there are only two groups of parameters in this section.

![[pic53.png|Differ]]

The first group allows you to specify an external file comparison program. Double Commander will automatically add the full filenames as the last launch parameters each time the differ tool is called.

Additionally: *Execute in terminal* and *Keep terminal window open after executing program* can be useful if you are using a console program and/or if the program's terminal output is important (or just temporarily for debugging).

*Position of frame panel after the comparison* – defines the order in which the filenames are passed to the comparison program (built-in or external):

- *Active frame panel on left, inactive on right* – The file from the active file panel will be opened in the left panel of the comparison program, the second file will be opened in the right panel.
- *Left frame panel on left, right on right* – The file from the left file panel will be opened in the left panel of the comparison program, the second file will be opened in the right panel.

If two files are selected in the active panel, the first file will be opened in the left panel of the comparison program.

**2.3.4. Tools > Terminal** ^ConfigToolsTerminal

This section contains terminal launch parameters:

![[pic54.png|Launch of the terminal]]

The first two groups are for running commands in the terminal (to indicate the position of commands to run on the command line, use `{command}` in the parameters field). They can be used in toolbar buttons, internal file associations, to launch external applications to [[Configuration#^ConfigTools|replace]] the built-in text editor, viewer and file comparison tool. You [[Configuration#^ConfigAssocEx|can add]] these actions to the file context menu (to the "Actions" submenu).

Also, the first group is used to open a file under the cursor in the terminal using `Shift+Enter` and to run a command from the command line (but if the [[Basic Help#2.11. Terminal window|Terminal window]] is enabled, the command will be executed in it).

The third group allows to specify the command that will be executed when the terminal is called (internal command [[Internal Commands#cm_RunTerm]], `F9` by default).

Default values:

- Windows: `cmd.exe`
- macOS: Double Commander will automatically detect the program specified in the system settings.
- Linux and other Unix-like systems:
  - For Debian and Debian-based distributions (Ubuntu, Linux Mint, antiX, Devuan and others), `x-terminal-emulator` will be used: this is a symbolic link to the terminal used in these systems by default.
  - Otherwise, Double Commander will try to get the value from the settings of the desktop environment: Cinnamon, GNOME, KDE, LXDE, LXQt, MATE or Xfce.
  - If automatic detection failed, Double Commander will use `xterm`.

**2.4. Fonts** ^ConfigFonts

![[pic28.png|Fonts]]

You can select fonts for the editor (`F4`), viewer (`F3`), file panels (*Main Font*) and other elements of the Double Commander interface, and also their size. The bottom line for each allows you to see how the display of the selected font looks. One important note: the fonts for the editor and viewer must be MONOSPACE. The figure below illustrates a proportionally spaced font in the window above (notice the strange spacing) and a monospace font in the window below which appears correctly spaced. Also, with some proportional fonts the characters may overwrite each other and look quite strange.

![[pic29.png|Font Differences]]

Normal (proportional) font above, monospaced below.

Also you can use `Ctrl`+mouse wheel to change the font size, this function works for the following interface elements or part of Double Commander:

- file list in left and right panels;
- current directory (address) bar;
- function key buttons bar;
- TreeView menu;
- search results in find files dialog;
- internal editor;
- internal viewer (if viewer shows text then this action will change font size, if image then action will work as zoom in/zoom out commands).

Also you can choose the type of font rasterization (regardless of the system settings), see description of [[doublecmd.xml Settings|<Quality>]].

**2.5. Colors** ^ConfigColor

This section contains color settings that are not included in other settings sections. The parameters are grouped by category.

![[pic59.png|Colors: Dark mode]]

1. *Dark mode* – enables or disables dark mode support (only macOS and Windows 10 1809 and newer). State:

- *Auto* – system settings will be used.
- *Enabled* – enable forcibly.
- *Disabled* – disable forcibly.

2. *Viewer* – color settings that are used by the built-in [[File Viewer|file viewer]] (see description of viewing modes [[File Viewer#2.3. "View"|here]]):

*Book Mode* – for the "Book" viewing mode, you can set the text color and background color.

*Image Mode*:

- *Background 1:* – sets the background color of the window when viewing images.
- *Background 2:* – if [[File Viewer#2.6. "Image"|Show transparency]] is enabled, the internal viewer indicates transparency using a checkerboard pattern as background and *Background 2* defines the color of the squares. If not set, the viewer will automatically calculate the value: for a dark background, light squares will be used and vice versa.

3. *Differ* – for the internal [[Basic Help#^cm_CompareContents|Differ tool]]: you can change the colors for added, deleted and modified lines, and the color for different characters in binary mode.

4. *Log* – options that set the text colors in the log window for informational messages, error messages, and messages about successful operations. Also, these colors are used in the window with the result of [[Basic Help#^cm_CheckSumVerify|verifying checksums]].

5. *Synchronize Directories* – for the internal [[Synchronize Directories|directory synchronization]] tool:

- *Left:* – files selected for copying or deleting on the left.
- *Right:* – files selected for copying or deleting on the right.
- *Unknown:* – files with the same names, but not identical.

6. *Drive Free Space Indicator* – here you can change the appearance of the drive free space indicator:

![[pic81.png|Colors: Free Space Indicator]]

Double Commander can display a gradient (from green to red) or simple monochrome indicator, in the second case you can choose the color and background. *Indicator Threshold Color* will be used if the free disk space is less than 10%.

The indicator example is clickable, so you can see how it will look.

**2.5.1. Colors > File panels** ^ConfigColorPanels

This section contains settings for the appearance of file panels:

![[pic30.png|Color settings]]

The color settings here are global settings for both file panels. These settings can be overridden by creating a customised column style which can have its own color settings, and more, for each tab in the panel! See [[Configuration#^ConfigColumns|Files views > Columns > Custom columns]] for details on how to do this. You should adjust the current style of the columns (*Default* by default) or create your own style and apply it for any tab.

Here you can choose colors that will be used to process the file panels: *Text Color*, *Background*, *Background 2*, *Mark Color*, *Cursor Color*, *Cursor Text*, *Inactive Cursor Color*, *Inactive Mark Color*, and also *Cursor border* (if you are not using a frame cursor). With the two background options you can make an alternating stripe in the panels, as in some screenshots.

*Use Inverted Selection* – inverts colors of marked text and marked text under cursor.

*Use Inactive Sel Color* – enables the display of the cursor also in the inactive panel.

*Use Frame Cursor* – Double Commander will use a frame instead of a solid rectangle.

*Allow Overcolor* enables the ability to use a color other than the default color for file names (see section [[Configuration#^ConfigColorFiles|Colors > File types]]).

In the *Current Path* parameter group, you can change the text color and background color of the [[Basic Help#2.6. Current directory bar|current directory bar]] for the active and inactive file panel.

Also here you can decrease the brightness of the inactive panel.

There is a preview area at the bottom of the window, so you can see all the changes at once.

The *Reset to DC default* button will reset all parameters to their default values.

The grid color can also be changed, but only manually. You need to close the application, open the [[Configuration#1. Configuration files|colors.json]] file and replace the value of the `GridLine` key in the `FilePanel` object. (Don't forget that the colors in `colors.json` are stored in two profiles: "Light" for light themes and "Dark" for dark themes.)
 About color format: Double Commander stores color values in the `$BBGGRR` format as a decimal number. For example, if you want to use the indigo color `#4B0082` (`$RRGGBB`), then do the rearrangement, you will get `82004B` and now you need to convert this hexadecimal number to decimal. Or you can temporarily add a color for some type of file (see below), find it in `colors.json` by name or mask, copy the value and delete.

**2.5.2. Colors > File types** ^ConfigColorFiles

Here you can specify file types that should be given a different color. The [[Configuration#^ConfigColorPanels|Allow Overcolor]] parameter must be enabled (enabled by default).

![[pic31.png|File types by color]]

In line *Category name* you may write a description of the file, what it does or what program it opens.

In line *Category mask* put a wildcard mask to match file types (symbol "*" means match any number of characters, symbol "?" means any one character). You may put multiple file types here using a semicolon ";" without spaces between them. Also you can use search templates (![[btemplate.png|Template...]]), including search with content plugins.

In line *Category attributes* you can put file attributes, and DC will match any files which have matching attributes (not available if using a search template). File attributes are specified by the following templates:

- Windows: [`d` or `l`]`rahs`[`c` or `e`]`tp`
- Unix/Linux: [`b`, `c`, `d`, `f`, `l` or `s`]`rwxrwxrwx`

i.e. the template must match the attribute text string in the file list. Description of values:

| Attributes in Windows |  |
| --- | --- |
| Attribute letter | What it stands for |
| a | archive |
| c | compressed (NTFS compression) |
| d | directory |
| e | encrypted (EFS encryption) |
| h | hidden |
| l | symlink |
| p | sparse |
| r | read only |
| s | system |
| t | temporary |

| Attributes in Unix/Linux (File Types) |  |
| --- | --- |
| File Types letters | What it stands for |
| b | block device |
| c | character device |
| d | directory |
| f | named pipe (FIFO) |
| l | symlink |
| s | socket |

The second part of the Unix/Linux template displays permissions: read (r), write (w), execute (x). The values are grouped in groups of three in the following order: user (owner), user's group, all others.

If attribute should not be set, it must be replaced with the "-" symbol, unnecessary attributes should be hidden: symbol "*" means match any number of characters, symbol "?" means any one character. For example, `?r*` (Windows) or `?r-*` (Linux) will find all read-only files and folders.

You can use a color from the list or specify yours using the ".." button.

Do not forget to click "Apply" button after customization.

Double Commander checks the list from top to bottom until the first match: a rule higher in the list will overlap any rule below.

**2.6. Keys** ^ConfigKeys

![[pic60.png|Keys]]

Here you can set the action on pressing some keys in the active file panel: *Letters*, *Alt+Letters*, *Ctrl+Alt+Letters*. You can choose one of the following actions: do nothing, set focus to command line and enter command, run

[[Basic Help#^cm_QuickSearch|quick search or quick filter]].

*Left, Right arrows change directory (Lynx-like movement)* – `right arrow` opens directory or runs a program under cursor, `left arrow` opens parent directory (only in the [[Basic Help#2.8. File Panels|full mode]]).

**2.6.1. Keys > Hot Keys** ^ConfigHotKeys

In this section you can set keys to launch commands and also specify parameters for these commands.

![[pic32.png|Hot Keys]]

*Shortcut files* – A drop-down menu containing a list of files with a set of hotkeys. They are stored in the directory with program settings files.

On the right is the file related menu button:

- Actions with the current file: *Save now*, *Rename*, *Copy* and *Delete*.
- *Restore DC default*.
- Commands for switching to the previous and next categories.
- Commands for switching the sort order of the command table (see below).

*Categories* – shows the category of hot key combinations: *Main*, *Copy/Move Dialog*, *Differ*, *Edit Comment Dialog*, *Editor*, *Find files*, *Multi-Rename Tool*, *Synchronize Directories*, *Viewer*.

*Filter* – enables you to search the internal commands more quickly.

*Sort order* – switchs the sort order of the command table:

- *By command name*.
- *By shortcut key (grouped)* – If multiple hotkeys are assigned, they will be listed separated by semicolon ";".
- *By shortcut key (one per row)*.

*Commands* – list of available [[Internal Commands|internal commands]] in Double Commander. The list is shown as a table with three columns:

- Command (name of internal command).
- Hotkeys (assigned shortcuts).
- Description (a short description).

The table at the bottom of the window shows assigned keyboard shortcuts, parameters, and interface elements (see below) for the selected command.

*Add hotkey* – will open a window for adding hotkeys.

*Edit hotkey* – will open the same window, but with the hotkey and other options already set.

*Delete hotkey* – will delete the hotkey selected in the list.

A window for adding hotkeys:

![[pic33.png|Add new hotkey]]

*Shortcuts* – new shortcut displays here. Click in the box and press combination on keyboard to enter new hot key. If the new combination is already being used for another command, Double Commander will show a warning.

*Parameters (each in a separate line):* – allows to set some parameters for the command. Most parameters must be added as *parameter=value* (unless otherwise stated), each must be in a separate line, without quotes and other ways of escaping special characters and spaces. The button below will open a description of the command in the [[Internal Commands|corresponding help file]] of Double Commander.

*Only for these controls* – The hotkey will only work if the selected interface element(s) has focus: command line, files or quick search panel.

The following buttons are located on the right side of the window:

- The *F1* button will show a menu with a list of free available keyboard shortcuts, grouped by alphabet and modifiers.
- The "+" button will add another field for the keyboard shortcut (up to five).
- The "-" button will delete last shortcut from list.

You can set multiple hotkeys for an internal command in two ways: use the *Add hotkey* button and then the "+" button several times or the *Add hotkey* button several times. The second way allows to use the selected command with different parameters.

**2.7. Mouse** ^ConfigMouse

![[pic61.png|Mouse]]

The first group of parameters is *Selection*:

- *Selection by mouse* – enables the ability to select and unselect files and folders with the mouse.
- *By clicking on icon* – allows to select files with one mouse click on their icons. Selection by clicking on icon in thumbnail view works when you click on left part (1/4 or 25%) of image.
- *Mode* – sets the left or right mouse button.

See the [[Basic Help#^select_files|Selecting files]] subsection for details.

*Scrolling* – the ability to use the mouse wheel to scroll the list of files in the panels:

- *Line by line with cursor movement* – cursor will move up or down the panel before scrolling takes place.
- *Line by line* – the cursor remains on the file and scrolling takes place immediately. Also you can specify the number of lines.
- *Page by page* – the same as previous, but scrolling is by pages rather than by lines (much faster scrolling).

*Open with* – will determine what will launch the action when you are using the mouse button on an element from the displayed file list in a panel:

- A double click is necessary to launch the action (default).
- A single click opens files and folders.
- A single click only opens folders. For files, a double click is needed.

*The text cursor no longer follows the mouse cursor* – is used for the last two values. If single click is enabled, by default the text cursor will follow the mouse cursor: this helps to avoid accidentally opening files or folders. You can disable it if you don't need it (or don't like it).

**2.7.1. Mouse > Drag & drop** ^ConfigMouseDD

This section contains settings related to [[Basic Help#^draganddrop|drag & drop]].

![[pic62.png|Mouse > Drag & drop]]

*Show confirmation dialog after drop* – helps to avoid accidental errors when using drag and drop files inside the active file panel or between panels: Double Commander will show a confirmation dialog as for normal copying or moving files.

The next feature is available in Windows only: you can drag and drop text selected in a web browser or word processor (for example, LibreOffice Writer or Microsoft Word) to the panel and save it. Here you can choose file format (RTF, HTML or plain text file), encoding and enable automatic name generation.

**2.8. Files views** ^ConfigView

In this section, you can set various file sorting options and date/time and size formats.

![[pic34.png|Files views: sorting and formatting]]

*Sort method* – sets the sorting method in the file panels:

- *Alphabetical, considering accents* – This method will sort alphabetically, taking into account the peculiarities of the system language and regional settings: also additional characters will be taken into account (for example, umlaut and other diacritical characters in Germanic languages or the letter "ё" in Russian).
- *Alphabetical with special characters sort* – Like the previous method, but additionally the list will be sorted by special characters and punctuation marks before letters.
- *Natural sorting: alphabetical and numbers* – This method will sort digits as numbers: for example, "3" will be show before "20" because 20 is larger than 3.
- *Natural with special characters sort* – Like the previous method, but also with sorting by special characters and punctuation marks.

*Case sensitivity* – complements the selected method:

- not case sensitive;
- according to locale settings (aAbBcC);
- first upper then lower case (ABCabc).

*Sorting directories* – sets the position of directories in the file list:

- sort by name and show first;
- sort like files and show first;
- sort like files.

*Insert new files* – sets the position of the new file in the list:

- at the top of the file list;
- after directories (if directories are sorted before files);
- at sorted position;
- at the bottom of the file list.

*Move updated files* – sets the position if the file property currently used for sorting was changed (modification date, size, etc.):

- don't change position;
- use the same setting as for new files;
- to sorted position.

The first parameter in the *Formatting* group is *Date and time format*. You can choose one of the existing templates from the drop-down list or set your own using date and time formatting characters. ^dt_format

Formatting characters are presented below (based on [Free Pascal documentation](https://www.freepascal.org/docs-html/rtl/sysutils/formatchars.html)). Some values depend on the regional settings of the operating system!

As example we will use 2021.01.24 09:06:02 (i.e. `yyyy.mm.dd hh:mm:ss`) and the USA region.

| Possible characters |  |  |
| --- | --- | --- |
| Characters | Description | Example |
| c | short date format and long time format if the time is not zero | 1/24/2021 9:06:02 |
| f | same as `c`, but adds the time even if it is zero | 1/24/2021 9:06:02 |
| d | day of month | 24 |
| dd | day of month (leading zero) | 24 |
| ddd | day of week (abbreviation) | Sun |
| dddd | day of week (full) | Sunday |
| ddddd | short date format | 1/24/2021 |
| dddddd | long date format | Sunday, January 24, 2021 |
| m | month or minutes if preceded by `h` or `hh` specifiers | 1 |
| mm | month or minutes if preceded by `h` or `hh` specifiers, with leading zero | 01 |
| mmm | month (abbreviation) | Jun |
| mmmm | month (full) | January |
| yy | year (two digits) | 21 |
| yyyy | year (with century) | 2021 |
| h | hour | 9 |
| hh | hour (leading zero) | 09 |
| n | minute | 6 |
| nn | minute (leading zero) | 06 |
| s | second | 2 |
| ss | second (leading zero) | 02 |
| z | milliseconds | 1 |
| zzz | milliseconds (leading zero) | 001 |
| t | short time format | 9:06 |
| tt | long time format | 9:06:02 |
| am/pm | use 12 hour clock and display am and pm accordingly (also `AM/PM`, `a/m` or `A/M`); for example, `t AM/PM` | 9:06 am |
| / | insert date separator | / |
| : | insert time separator | : |
| "text" | literal text; for example, `yyyy "AD"` | 2021 AD |

The next parameters sets the file size format:

- *File size format* – will be used in the file panels.
- *Header format* – will be used in the drives list and free space label.
- *Footer format* – will be used in the status bar of the file panels.
- *Operation size format* – will be used in the file operations dialogs: copying, moving, calculating checksums and so on.

Also on the right you can set the number of digits after the decimal separator (i.e. separator for integer and fractional parts of a number): 0, 1, 2 or 3.

File size units: bytes, kilobytes, megabytes, gigabytes, terabytes or float (Double Commander will choose the unit automatically based on the size).

"Personalized" in the name means that Double Commander will use *Personalized abbreviations* from the list below. The *Default* button will reset their to the default values for the selected language (specified in the corresponding language file).

**2.8.1. Files views > Files views extra** ^ConfigViewEx

![[pic63.png|Files views extra]]

Marking/Unmarking entries:

- *Windows style filter when marking files ("*.*" also select files without extension, etc.)* – By default, the mask "*.*" matches the name of any file that has an extension, for any file names use the mask "*". If enabled, the mask "*.*" will match any file.
- *Default attribute mask value to use* – will be used for the following commands: *Select All* (`cm_MarkMarkAll`), *Unselect All* (`cm_MarkUnmarkAll`), *Invert Selection* (`cm_MarkInvert`), *Select a Group* (`cm_MarkPlus`) and *Unselect a Group* (`cm_MarkMinus`). For example, if you want these commands to work only with files, specify `d-`. The *Add* button will open the file attributes selection window, you can use it or enter them manually. For more information about file attributes and their use, see [[Find Files#3.1. Searching for files with specific attributes.|here]].
- *Use an independent attribute filter in mask input dialog each time* – If enabled, the attribute filter will be added to the *Select a Group* (`cm_MarkPlus`) and *Unselect a Group* (`cm_MarkMinus`) command dialogs.

*When selecting files with <SPACEBAR>, move down to next file (as with <INSERT>)* – moves the cursor down on selection with the `Space` key. Default keys are `Shift+Down` or `Shift+Up`.

*Show square brackets around directories* – helps to visually distinguish directories from files when icons are disabled. Also you can use any symbols instead them, see description of `<FolderPrefix>` and `<FolderPostfix>` parameters [[doublecmd.xml Settings|here]].

*Show system and hidden files* – If enabled, Double Commander will show files and folders which have the "hidden" or "system" attribute (Windows) or the name with a dot character in the beginning (Linux and other Unix-like systems). This can also can be changed from the [[Basic Help#^cm_ShowSysFiles|main menu]]. ^show_hidden

The parameters *Load file list in separate thread* and *Load icons after file list* are designed to speed up the display of the list of files in the panel, i.e.the application window will hang less when opening large directories.

*Don't load file list until a tab is activated* – When launched, Double Commander will not load the list of files of inactive tabs that were opened in the previous session.

*Highlight new and updated files* – If enabled, the names of files that are currently being created or modified will flash.

*Enable inplace renaming when clicking twice on a name* – is an additional ability to rename the file using the left mouse click (it does not depend on the the chosen key for selection with the mouse), as in Windows Explorer. After clicking, the mouse cursor must stay still for at least one second. In the [[Configuration#^ConfigMouse|mouse settings]] section, double click for files and folders or just files should be selected.

*Enable changing to parent folder when double-clicking on empty part of file view* – is an additional feature to simplify directory navigation. But not applicable if you are using a column set and the list of files in the current directory does not fit in the panel (i.e. you see a vertical scroll bar).

**2.8.2. Files views > Brief** ^ConfigViewBrief

There are only two parameters here.

![[pic64.png|Files views > Brief]]

*Show file extensions*: *directly after filename* or *aligned (with Tab)*. In the second case, file extensions will be shown separately, aligned to the right side of the columns.

*Columns size*: Double Commander will set the size automatically (the size will depend on the length of the filenames) or you can set the width of the columns (in pixels) or their count.

**2.8.3. Files views > Columns** ^ConfigViewFull

![[pic65.png|Files views > Columns]]

First group is *Show grid*:

- *Vertical lines* – enables vertical grid lines in the panels.
- *Horizontal lines* – enables horizontal grid lines in the panels.

The screenshots below illustrate this subtle grid effect. The screenshot on the left has the vertical and horizontal lines enabled and the screenshot on the right does not.

![[pic35.png|with and without lines]]

It is possible to change the color of the lines, see more details [[Configuration#^ConfigColorPanels|here]].

*Auto fill columns* – If enabled, when resizing the window (or if free space exists), Double Commander will resize the column, which selected in the next option *Auto size column:* (first or last). The horizontal scrollbar will not be available.

*Column titles alignment like values* – If enabled, Double Commander will align the column header the same as the content (instead of left-aligned).

If the content of the column is larger than its width:

- *Cut text to column width* – Sometimes column text can overlap into other columns. This option truncates any extra text at the column boundary.
- *Extend cell width if text is not fitting into column* – If the text does not fit and the adjacent cell is empty, then the text will also occupy the adjacent cell.

**2.8.3.1. Files views > Columns > Custom columns** ^ConfigColumns

In this section you can customize the panel appearance, columns, colors, fonts, etc. Double Commander is very configurable in this way.

![[pic36.png|Custom columns]]

There is a preview area at the bottom of the window, so you can see all the changes at once. You may move cursor and select files to get immediately an actual look and feel of the various settings.

*File system* – allows to switch to columns settings for WFX plugins (if installed plugins support it).

*Columns view* – a list of existing column styles. There is one default style *Default*.

*Save* – saves changes in the selected set of columns.

*Save as* – allows to save the selected column set (as is or with changes) with a new name.

*New* – creates a new column set based on the selected one. With the same name + current date and time.

*Rename* – will prompt to enter a new name.

*Delete* – deletes selected column set.

Below is a table with columns of the selected set, here you can set the number, name, content, place and size of columns. The count of lines in the table is equal to the count of columns in the set. Adding a new column: use the `down arrow` key or right-click in the empty area near the table and select *Add column*.

These are the parameters that determine the table for the column (click in the boxes to edit them):

![[pic37.png|Columns]]

*Column* – shows the indicator of the selected column.

*Caption* – specifies the name of the column which will be displayed in the [[Basic Help#2.7. Tabstop headers bar|tabstop headers bar]]. You can set any name you like.

*Width* – column width (in pixels) which will be set on program start. Note: the width depends on the column content, e.g. the file extension column will have a small width.

*Align* – sets the alignment of the content of the column. Variants are:

- `"<-"` – align left;
- `"->"` – align right;
- `"="` – align middle.

*Field contents* – sets the basic content of the column. When a cell is selected, the "+" button will appear on its right side, you can choose internal fields of Double Commander (submenu "DC") or fields of installed WDX plugins (submenu "Plugins"). List of internal fields:

- `GETFILENAME` – file name and extension (`text.txt`).
- `GETFILENAMENOEXT` – file name and no extension (`text`).
- `GETFILEEXT` – file extension (from the dot to the end, e.g. `txt`).
- `GETFILESIZE` – file or directory size. By default, the appearance will depend on the option chosen in the [[Configuration#^ConfigView|Files views]] section, but all possible size formats are also available.
- `GETFILETIME` – file or directory modification date.
- `GETFILECREATIONTIME` – file or directory creation date.
- `GETFILELASTACCESSTIME` – file or directory last access date.
- `GETFILECHANGETIME` – file or directory status change date.
- `GETFILEATTR` – file or directory attributes. You can choose a string or numeric (octal) value. In Windows, an octal value can be used if Unix attributes are displayed in the file panel (for example, with the FTP plugin). For a detailed description of the string value, see [[Configuration#^ConfigColorFiles|here]].
- `GETFILEPATH` – path to the current item. Uses: usually, for search results.
- `GETFILEGROUP` – displays the group of the file owner.
- `GETFILEOWNER` – displays the owner of the file.
- `GETFILELINKTO` – displays the path and file, that is, what is linked with this symlink.
- `GETFILETYPE` – file type (as in Windows Explorer or MIME-type).
- `GETFILECOMMENT` – file or directory description (comment) from `descript.ion` (see details [[Basic Help#^cm_EditComment|here]]).
- `GETFILECOMPRESSEDSIZE` – compressed file size (real size if using NTFS compression).

By default, fields with timestamps use the date and time format that was choosen in the [[Configuration#^ConfigView|Files views]] settings section. You can also specify your preferred format directly in the column inside the curly brackets, using the same [[Configuration#^dt_format|date and time formatting characters]].

*Move* – allows to move lines (which equates to reordering the columns). Click twice in the Move box and you will see a type of spinner appear, clicking on the upper part moves the line up (column moves left).

*Delete* – allows to remove any line. To delete: click in the Delete box of the line. Then click again, this time a delete symbol appears. If you click a third time the line will be deleted from the table.

Next, you can change the appearance of the file panels.

*Go to set default* – opens the section [[Configuration#^ConfigColorPanels|Colors > File panels]].

*Use custom font and color for this view* – allows to change the appearance of file panels only for this set of columns (and separately for each column, if needed). You can override the font for the file panels and the global settings from [[Configuration#^ConfigColorPanels|Colors > File panels]]:

![[pic38.png|Custom font and color]]

Note: *Cursor border* and *Use Frame Cursor* can be applied only for the whole set.

*Previous*, *Next* – switches columns.

*Customize column* – shows the name of the custom column.

*>>* – button for choosing any color from the palette.

*R* – restores default value.

*All* – applies the modification to all the other columns.

**2.9. Plugins** ^ConfigPlugins

Plugins are extensions that enhance the functionality of Double Commander.

In the beginning, a few general settings.

![[pic66.png|Plugins]]

*When adding a new plugin, automatically go in tweak window* – See the description of the *Tweak* button below.

*Plugin filename style when adding a new plugin* – Here you can choose how the path will be set when adding plugins:

- With complete absolute path.
- Path relative to [[Variables in Parameters#16. Environment variables|%COMMANDER_PATH%]].
- Relative to the specified path.

Also you can apply the chosen way to the already added plugins.

*Lua library file to use* – the full name of the Lua library, or only the file name if the file is located in the program directory or system directories for libraries. This path may be relative to the Double Commander executable file. (Lua scripts can be used for automation and as content plugins, see more details [[Lua Scripting|here]].) ^luapathtolibrary

There are several types of plugins:

*1. Packer plugins (WCX)*

Packer plugins are used to unpack specific types of files, usually archive formats. Some plugins also support creating new archives and modifying existing archives.
 There are plugins that allow to save a list of selected files or use batch processing: creating links,converting files, copying with specific conditions, etc.
 Order matters: when choosing an appropriate plugin, Double Commander starts checking by extension from top to bottom. Use the *By extension/By plugin* button to switch list view and drag and drop.

*2. Content plugins (WDX)*

Content plugins are designed to get properties of a file or information about its content (for example, EXIF or ID3 tags). You can use this data in the file search or multi-rename tool, column set, tooltips.
 Also Double Commander supports content plugins written in the Lua language (scripts are added in the same way as ordinary plugins). Examples can be found in the program folder (`plugins/wdx/scripts`).

*3. File system plugins (WFX)*

File system plugins uses their own file systems or provides access to other file systems and devices (local or remote). For example, FTP servers, network directories, mobile devises. Also it can be lists of files, running processes and services, or the Windows registry.

*4. Lister plugins (WLX)*

The built-in viewer displays plain text files, some image formats and console commands output, plugins allow to expand this list: electronic documents and databases, audio and video files, font files, content of archives, detailed information about some files, source code files with syntax highlighting.
 Order matters: when choosing an appropriate plugin, Double Commander starts checking from top to bottom.

*5. Search plugin (DSX)*

Search plugins are Double Commander's own plugin type, these plugins use console programs to find files (for example, Locate, Everything or Recoll). The DSX plugins interface allows to send them [[Find Files|search parameter values]] from the "Standard" and "Advanced" tabs.

Buttons:

- *Add* – opens the file selection dialog. Alternatively, you can use the internal command [[Internal Commands#cm_AddPlugin]] (also plugins can be installed automatically).
- *Disable* – allows to temporarily disable the selected plugin.
- *Remove* – removes the selected plugin from the list (but not plugin file!).
- *Tweak* – the action depends on the type of plugin:
  - WCX: change plugin path, set file extensions and supported functions;
  - WDX and WLX: change plugin path, display name or detect string;
  - WFX: change plugin path or display name.
- *Configure* – opens the plugin's own settings window (if selected plugin supports this feature).

Double Commander supports the use of a master password to protect passwords in WCX and WFX plugins (if the plugin developer has provided for the use of this feature). This is convenient because your passwords will be protected by encryption and you need to remember only one password. Passwords are encrypted twice, first using Blowfish (448 bits) and then using AES (256 bits).

Note: At the moment, Double Commander does not support changing the master password: if necessary, you will need to disable the use of the master password in the plugin settings, close the program, open the [[Configuration#^ConfigDC|directory with the configuration files]], delete the `pwd.ini` file, run the program again and enable the master password in the plugin settings. To delete outdated or unnecessary saved passwords, you will need to close the program and manually edit the `pwd.ini` file.

**2.10. Layout** ^ConfigLayout

![[pic39.png|Layout]]

You can change the layout of the main window here. I suppose, all the available options are explained on the screenshot above (Layout). The screenshot below illustrates what DC looks like with all the layout options unselected.

![[pic40.png|Layout DC]]

**2.10.1. Layout > Drives list button** ^ConfigDrivesList

![[pic67.png|Drives list button]]

In this section you can choose which additional information Double Commander will show in the [[Basic Help#2.4. Drives list|drives list menu]]: drive label, file system and free space.

**2.10.2. Layout > Tree View Menu** ^ConfigTreeMenu

In this section you can enable the Tree View Menu and choose where it will be used.

![[pic68.png|Tree View Menu settings]]

The Tree View Menu is a way to display some of the Double Commander menus as a tree in a separate window: Directory Hotlist, Favorite Tabs, directory and command line history. This way of presenting content and a filter will help you quickly select the desired menu item.

![[pic41.png|Tree View Menu]]

Using the parameters of the corresponding internal commands, you can set the position of the Tree View Menu:

- menu will be shown from the top left corner of active panel;
- menu will be shown at the current mouse cursor position.

Parameters can be specified in the [[Configuration#^ConfigHotKeys|hotkey settings]] or add a button on the [[Toolbar|toolbar]].

Also Double Commander can display main menu and toolbar as a tree (always in the center of its window), see the description of commands [[Internal Commands#cm_ShowMainMenu]] and [[Internal Commands#cm_ShowButtonMenu]].

**2.10.3. Layout > Tree View Menu Colors** ^ConfigTreeMenuColor

Here you can customize the appearance of the menu to your preference, a preview will show all changes before saving.

![[pic69.png|Tree View Menu Colors]]

**2.11. Toolbar** and **Toolbar > Toolbar Middle** ^ConfigToolbar

See the dedicated [[Toolbar]] help page about how to use and configure it.

**2.11.2. Toolbar > Toolbar Extra** ^ConfigToolbarEx

![[pic70.png|Toolbar Extra]]

In this section you can choose how the path will be set when adding icons, commands and starting paths:

- With complete absolute path.
- Path relative to [[Variables in Parameters#16. Environment variables|%COMMANDER_PATH%]].
- Relative to the specified path.

Also you can apply the chosen way to the already added paths.

**2.12. File operations** ^ConfigOperations

This section contains settings related to file manipulation.

![[pic71.png|File operations]]

*Show operations progress initially in* – sets the initial display way and position of the file operations progress:

- separate window;
- minimized separate window;
- operations panel: the special panel above the function key buttons bar will be used
  ![[pic42.png|Operations panel]]
  (you can switch to display progress in a separate window by clicking on it with the mouse).

*Drop readonly flag* – If enabled, Double Commander will drop this flag in Windows, and add "w" attribute in Linux. This is handy if copying files from CD/DVD media where the files would retain the read-only attribute by default.

*Select file name without extension when renaming* – If enabled, renaming with the `F2` key will select all characters in the file name up to the last dot, otherwise the entire file name will be selected.

*Show tab select panel in copy/move dialog* – If the target panel has more than one tab, on copy/move you can choose the destination tab:

![[pic43.png|Tabs in copy/move dialog]]

*Delete to recycle bin (Shift key reverses this setting)* – If enabled, Double Commander will delete the selected files or the file under the cursor to trash (recycle bin) when you press `F8` or `Del` and will delete permanently when you use `Shift+F8` or `Shift+Del`. If unchecked, the behavior of this keys will be inverted.

*Show confirmation window for* – allows to choose the file operations for which Double Commander will show confirmation dialogs. The maximum secure behavior is chosen by default. Keep in mind that this group of parameters is not taken into account when you use [[Basic Help#^draganddrop|drag & drop]]: in this case, Double Commander uses an independent parameter in the [Mouse > Drag & drop](ConfigMouseDD) settings section.

The following parameters are directly related to the execution of operations.

The *Buffer size for file operations (in KB)* and *Buffer size for hash calculation (in KB)* parameters set the size of the allocated memory for operations such as copying, moving, splitting or combining files, searching for files by content and calculating checksums. You should keep in mind that there is no universal value, but you can try to find a more suitable size.
 Note: The first parameter is not used in the copy function in Windows, since the system function is used for copying.

*Number of wipe passes* – Here you can specify the number of rewrites to [[Basic Help#^cm_Wipe|secure delete files]].

*Process comments with files/folders* – If enabled and you have a file/folder with a [[Basic Help#^cm_EditComment|comment]] attached and you copy or move it to another folder the comment will be copied or moved to the destination along with the file/folder.

*Skip file operations errors and write them to log window* – If a file operation error should occur the error message will appear in the log window below the panels rather than appearing in a popup dialog. This can be useful because the error window will suspend the operation. In the [[Configuration#^ConfigLog|Log]] settings section, you can limit the total number of messages, allowing only messages with the "Error" status.
 The parameter is taken into account in most file operations: copying, moving, deleting, erasing, combining and splitting files, setting file properties (timestamps, owner, attributes), calculating checksum, as well as file operations when working with archives, WFX plugins and GVfs.

*Duplicated name auto-rename style* – sets the file auto-renaming template if a file with the same name already exists in the target directory (i.e. when you choose *Auto-rename source files* or *Auto-rename target files* in the copy/move dialog): "Copy (x) filename.ext", "filename (x).ext" or "filename(x).ext", where "x" is a counter (2, 3, 4 and so on).

**2.12.1. File operations > File search** ^ConfigSearch

See description on the [[Find Files#7. Additional configuration|Find files]] help page.

**2.12.2. File operations > Multi-Rename** ^ConfigRename

See description on the [[Multi-Rename Tool#10. Additional configuration|Multi-Rename Tool]] help page.

**2.13. Folder tabs** ^ConfigTabs

![[pic72.png|Folder tabs]]

*Show tab header also when there is only one tab* – If this option is disabled and there is only one tab on the panel, a tab header won't appear (usually this is more visually attractive).

*Tabs on multiple lines* (Windows only) – If the folder tabs do not fit in one line, then they will be placed in several lines. Otherwise, buttons to scroll them will be shown on the right (GTK2: on the right and left).

*Limit tab title length to* – Tabs with long names will be limited to this length and the displayed name will be truncated if longer than this value.

*Confirm close locked tabs* – If enabled then it will prompt for confirmation that you wish to close locked tab. Otherwise, such a tab will be closed as usual tab.

*Confirm close all tabs* – If selected and a [[Basic Help#^cm_CloseAllTabs|Close All Tabs]] command is executed this option will prompt for confirmation that you wish to remove all inactive tabs. ^5_1_11_0_vopros

*Close duplicate tabs when closing application* – If enabled, Double Commander will check the list of opened tabs and close duplicate tabs (separately for each panel!), only the first of them will be saved (counting from the left).

*Ctrl+Up opens new tab in foreground* – this option changes the behavior of the command [[Basic Help#^cm_OpenDirInNewTab|Open folder in new tab]] (`cm_OpenDirInNewTab`): if enabled then Double Commander will open a new tab for the directory under the cursor and will switches to this tab. ^5_1_11_2_vopros

*Open new tabs near current tab* – If enabled, new tab will be created on the right next to the currently active tab. If not, new tabs will be added to the right after the last tab.

*Reuse existing tab when possible* – For locked tab with directory change in new tab: if the selected folder is already open on any tab, then this tab will be activated instead of creating a new tab.

*Show tab close button* (Unix-like systems only) – If selected, a small "x" button will appear on tabs allowing to click on it to close them. ^5_1_11_3_vopros

*Show locked tabs with an asterisk ** – to distinguish between locked and unlocked tabs. Locked tabs will be marked by "*". Tab `Downloads` is locked: ^5_1_12_1_zvezda

![[pic6.png|Tabs]]

*Keep renamed name when unlocking a tab* – When you change the state of a tab from "locked tab" on "normal tab", Double Commander returns the usual tab name (current folder name): this option allows to keep the changed name.

*Activate target panel when clicking on one of its Tabs* – If enabled, when you click the mouse on a tab on the other panel, the focus will automatically be transferred to it (it will become the active panel). Also the cursor position will be retained when switching between panels this way.

*Always show drive letter in tab title* (Windows only) – Show drive letter and a colon before the folder name, e.g. "c:plugins".

*Tabs position* – Place folder tabs at the top or bottom of file panels.

*Action to do when double click on a tab:* – You can choose one of the following actions:

- do nothing;
- close this tab;
- access Favorite Tabs (save current tabs, load saved set or configure);
- show the tabs popup menu with the same items as in the [[Basic Help#2.1.5. "Tabs"|"Tabs"]] menu.

**2.13.1. Folder tabs > Favorite Tabs** ^ConfigFavoriteTabs

The list of saved tab sets is available in the [[Basic Help#2.1.6. "Favorites"|"Favorites"]] menu and in the popup menu called by the [[Internal Commands#cm_LoadFavoriteTabs]] command.

In this section you can manage them: change order, names, delete unnecessary, sort or group in a submenu.

![[pic73.png|Favorite Tabs]]

Also you can export entries to the selected directory and import them. Each entries will be saved to a separate .tab file (if it necessary, tabs from such a file can be loaded using the [[Internal Commands#cm_LoadTabs]] command).

Some typical actions are added in the context menu of entries.

**2.13.2. Folder tabs > Folder tabs extra** ^ConfigTabsEx

This section contains additional settings for Favorite Tabs.

![[pic74.png|Folder tabs extra]]

*Enable Favorite Tabs extra options (select target side when restore, etc.)* – By default, saved tabs will be restored in the same panel and they will replace all opened tabs, you can change it with:

- *Tabs saved on left will be restored to:*
- *Tabs saved on right will be restored to:*
- *When restoring tab, existing tabs to keep:* – i.e. the Favorite Tabs will be added to the already open tabs.

The following values are available for each parameter: *Left*, *Right*, *Active*, *Inactive*, *Both* or *None*.

*Keep saving dir history with Favorite Tabs* – enables or disables saving the history of visited directories for each tab.

Also you can apply these parameters separately for each tabs set.

*Default position in menu when saving a new Favorite Tabs* – determines the order of adding a new set:

- Add at beginning
- Add at the end.
- Alphabetical order.

You can also choose to automatically open the [[Configuration#^ConfigFavoriteTabs|Favorite Tabs]] settings section after saving a new or resaving the current set:

- *Goto to Favorite Tabs Configuration after saving a new one*.
- *Goto to Favorite Tabs Configuration after resaving*.

**2.14. Log** ^ConfigLog

Here you can choose the filename to log Double Commander's operations (copying or moving files, creating directories, launching external applications and so on). Also you can choose which operations will be logged.

![[pic44.png|Log]]

If *Include date in log filename* is enabled, Double Commander will create a separate file for each day. In this case, you can set the number of log files: older files will be deleted automatically.

**2.15. Configuration** ^ConfigDC

![[pic75.png|Configuration]]

*Location of configuration files* – Here you can choose where to store all configuration files (also you can see the full path here):

- The "settings" folder in the program directory (portable version).
- User home directory.

As an indicator, Double Commander uses an empty `doublecmd.inf` file in the "settings" folder in the program directory: if the file exists, Double Commander will load configuration files from the "settings" folder and save them here, otherwise Double Commander will use the current user's folder. You can manually add the `doublecmd.inf` file and get a portable version, or delete it by switching the storage method to the user's folder.

If you launch Double Commander with the [[Command Line|--config-dir]] parameter, then DC will just write *Set on command line* and show the full path to the configuration files.

To quickly navigate to the directory with configuration files, you can use the *Special Dirs* submenu in the [[Directory Hotlist]] menu or use the [[Variables in Parameters#16. Environment variables|%DC_CONFIG_PATH%]] variable.

Buttons *Edit* and *Apply* – allow to open the `doublecmd.xml` configuration file and change the settings manually. Keep in mind that some settings require a restart of Double Commander to apply.

Note (or little trick): This way allows to apply settings immediately without restarting the DC (but not all!): for example, you can change and immediately apply the size of the icons in the file panels, but you will not be able to change the program language without restarting.

*Save on exit* – Here you can choose what Double Commander will save on exit. Checkbox *Save configuration* enables or disables saving:

- *Main window state* – Size and position of the application window.
- *Folder tabs* – List of tabs that are open in the left and right panels.
- *Search/Replace history* – [[Find Files|File search]] history (except for file name masks, see below), history of masks in the [[Multi-Rename Tool]] and history of searching and replacing text: search by file contents, viewer, built-in editor and built-in differ, search and replace in directory hotlist and toolbar settings. The state of the text search options (*Case sensitive*, *Regular expressions* and *Hexadecimal*) for each entry is also saved.
- *Directory history* – List of all visited directories (see note below).
- *Command line history* – Commands that were used at the [[Basic Help#2.10. Command line|command line]].
- *File mask history* – Double Commander saves a general history of used file masks for several tools: find files, filters in [[Synchronize Directories|directory synchronization]] and [[Basic Help#^cm_ExtractFiles|archive unpacking]], commands for [[Basic Help#^cm_MarkPlus|selecting and deselecting a group of files]].

The maximum number of entries in history is limited to 50.

Note about the history of visited directories: During the session, Double Commander stores up to 255 visited directories in memory (however, when the program is closed, only the last 50 entries will be saved). You can change the number of history entries in the popup menu when calling the [[Internal Commands#cm_DirHistory]] command (default value is 30, see the `Count` attribute in the [[doublecmd.xml Settings|<DirHistory>]] tag), but when using the [[Configuration#^ConfigTreeMenu|Tree View Menu]], all available history will be shown.

Note: Search templates are not related to the history and are saved separately (in the `doublecmd.xml` configuration file). To manage the list of templates, you can use the [[Find Files#5. Tab "Load/Save"|file search]] tool.

You can choose how the list of settings sections will look:

- *Sort order of configuration order in left tree* – You can choose classic (as in the source code of Double Commander and help) or alphabetical. In both cases, the **Language** section will be the first.
- *Tree state when entering in configuration page* – expand the whole tree or collapse.

*Directories* – Here you can see a list of directories that Double Commander can use to store thumbnail cache, icon themes and syntax highlighting files for the internal editor. You cannot change them, it's just information.
 If portable mode is used, Double Commander will only use the corresponding folders ("cache", "pixmaps" and "highlighters") in the program directory. Also in this mode, the "plugins" folder in the program directory will be used for automatic installation of plugins (see details [[Internal Commands#cm_AddPlugin|here]]).

**2.16. Quick search/filter** ^ConfigQuick

This section contains the settings of the [[Basic Help#^cm_QuickSearch|quick search/filter]] tool. Quick search is used in searching for filenames in the panel, quick filter will hide all filenames that do not match the conditions.

![[pic45.png|Quick search/filter]]

Exact name match:

- *Beginning (name must start with first typed character)* – means that the typed text will match the "text*" mask, where "*" is any number of any characters.
- *Ending (last character before a typed dot . must match)* – If there is a dot among the typed characters, the name must end with those characters. For example, if you typed "dx.l", the file mask will be "*dx.l*".

If nothing is checked, the typed characters can be located in any part of the file name.

I like to have the *Beginning (name must start with first typed character)* selected and then I can just type the first character of the filename I'm looking for and then the second character, etc. The file is quickly located in this manner.

Below you can set the case sensitivity and choose what you want to search: only files or directories, or both.

These options can be changed on the fly directly in the quick search/filter bar. Also you can toggle between search and filter.

Options:

- *Hide filter panel when not focused* – The quick search/filter panel will hide automatically as soon as you move the focus to the file panel. In [[Basic Help#2.8. File Panels|brief view]] hiding the panel does not work correctly, so the option is ignored until a suitable solution is found.
- *Keep saving setting modifications for next session* – By default, all parameters that have been changed in the quick search panel will be kept in memory only until the program is closed, the option allows to change this behavior.

**2.17. Miscellaneous** ^ConfigMisc

This section contains parameters for which there was no suitable place in other sections of the settings:

![[pic46.png|Miscellaneous]]

*Show splash screen* – If enabled, before displaying the main window, Double Commander will show a splash screen containing the program icon and version, compilation date, and the version of Lazarus, FPC, and operating system.

*Show warning messages ("OK" button only)* – shows warning messages if enabled. (For example, if Double Commander cannot set some property or attribute of a file due to file system restrictions in the target directory.)

*Always go to the root of a drive when changing drives* – If unchecked, Double Commander will go to the last open directory on this drive (in this case, you can go to the root directory of the drive by pressing its button twice).

*Show current directory in the main window title bar* – If enabled, Double Commander will display the name of the current folder and the active panel path in the main window title bar.

*Default single-byte text encoding:* – By default (NONE), the built-in file viewer and the built-in editor use automatic encoding detection, but you can specify one of the supported single-byte encodings as the default value. This parameter does not affect the automatic detection of multibyte encodings (UTF-8, UTF-16 and others). Special values are also available:

- *ANSI* – default system ANSI encoding (depends on the system locale).
- *OEM* – default system OEM (DOS) encoding (depends on the system locale).

*Thumbnails* – Here you can set the thumbnail size of the images and enable saving the thumbnail cache (otherwise, the thumbnail cache will be stored in memory only until the program is closed). The parameter values are used in the corresponding [[Basic Help#2.8. File Panels|file list view mode]] and in the built-in [[File Viewer#5. Preview|viewer]]. The thumbnail cache directory can be found in the [[Configuration#^ConfigDC|Configuration]] section. Double Commander uses PNG or JPEG (only for .bmp, .jpg and .jpeg) formats. The thumbnail name is the MD5 sum of the full name of the source file. The full name of the source file, its size and modification date will be added to the file.

The *Remove thumbnails for no longer existing files* button will help to remove obsolete thumbnails.

*File comments (descript.ion)* – Here you can set the default encoding for existing [[Basic Help#^cm_EditComment|file comments]] (OEM, ANSI or UTF-8) and the encoding for new files (UTF-8 BOM, UTF-16 LE or UTF-16 BE).

The next group of parameters is used for import from Total Commander and export [[Directory Hotlist#3.3. Exporting/Importing to/from Total Commander|Directory Hotlist]] and [[Toolbar|toolbar]]: the path and name of the Total Commander executable file and the main configuration file, as well as the directory where the toolbar files are located.

**2.18. Auto refresh** ^ConfigRefresh

Allows Double Commander to refresh panels automatically, same as the `Ctrl+R` manual refresh command does.

![[pic76.png|Auto refresh]]

*Refresh file list* – specifies what events Double Commander should react to and update the list of files and status bar:

- When files are created, deleted or renamed.
- When size, date or attributes change.

If it possible, Double Commander makes the appropriate change to the list of files, otherwise it completely rereads the list of files. If there are a large number of changes (if more than a quarter of the files are affected or the total number of changes exceeds 100), the list of files will be reread completely.

Note: This function may not work inside mounted network directories.

If both options are disabled, Double Commander will not watch changes made by third-party applications, and after changes made in the program in the file system, it will reread the entire list of files.

In virtual file systems (WFX plugins, GVfs), Double Commander rereads the entire list of files when you create, delete, or rename a file.

Note: Keep in mind that the final result may depend on the value of the *Insert new files* and *Move updated files* parameters in the [[Configuration#^ConfigView|Files views]] settings section.

Also you can disable auto-refresh:

- When Double Commander window is in the background or minimized.
- For the specified paths and their subdirectories, just list them separated by semicolons ";" without spaces (e.g. `/home;/media/cdrom`).

**2.19. Icons** ^ConfigIcons

![[pic77.png|Icons]]

The first option enables the display of the file type icons to the left of the name:

- *All associated + EXE/LNK (slow)* – Same as *All*, but additionally: icons from .exe, .ico, .cur, .ani and shortcuts (Windows), application icons from application catalogs (i.e. .app, macOS), .desktop and .directory (Linux and other Unix-like systems). Also DC will show the folder icon specified in the `desktop.ini` (Windows) and `.directory` (Linux) files.
- *All* – Icons for all file types associated with any program will be displayed (from system settings and Double Commander [[Configuration#^ConfigAssociations|file associations]]).
- *Only standard icons* – Only the icons listed in the `pixmaps.txt` file and the icons from the file association settings will be displayed. In this case, you can use icons only from the Double Commander icon theme (see directories `pixmaps/dctheme/XxX/mimetypes` in the program folder) or specify the full (with path) file name. Creating an icon theme is described in the [[FAQ#^theme|FAQ]].
- *No icons*.

*Show overlay icons, e.g. for links* – If enabled, Double Commander will show overlay icons such as arrows for .lnk files and links.

*Dimmed hidden files (slower)* – If enabled, Double Commander will show icons for hidden files with 50% transparency.

*Disable special icons* – You can disable the loading of special icons (overlay icons, icons from .exe/.lnk files) for the specified directories and their subdirectories, just list them separated by semicolons ";" without spaces.

*Icon size* – You can choose from the following sizes:

- *File panel* – 16x16, 24x24, 32x32 or 48x48.
- *Disk panel* – 16x16, 24x24 or 32x32.
- *Main menu* – 16x16, 24x24 or 32x32.

*Show icons on buttons* – If enabled, Double Commander will show icons on the buttons of the dialog windows (*OK*, *Cancel*, *Start*, *Add To Queue* and so on).

*Show icons for actions in menus* – If enabled, Double Commander will show icons in the main menu of the application window and the Multi-Rename Tool. This option also enables the display of a submenu icon in the Directory Hotlist and Favorite Tabs menus.

In the last parameter, *Icon theme*, you can choose an icon set from the drop-down menu. Double Commander does comes with one *DCTheme* icon theme, but you can create and add your own, see the [[FAQ#^theme|FAQ]] for details.

Note: In Unix-like systems, Double Commander will primarily use the system icon theme, if some icons does not exist, it will use its own.

**2.20. Ignore list** ^ConfigIgnore

Ignore specific files and folders (one per line): they will not be displayed in panels.

![[pic78.png|Ignore list]]

- You can use full path to file or filename.
- Supports the wildcards "*" and "?" (symbol "*" means match any number of characters, symbol "?" means any one character).
- When a mask is ended with a directory separator, it will match only directories.

*Save in:* – the ignore list location (by default it's `ignorelist.txt` near `doublecmd.xml`).

*Add selected names with full path* – will add all files/folders which selected in the active panel (if exists) or file under cursor with full path.

*Add selected names* – will add names of all files/folders which selected in the active panel (if exists) or file under cursor. This means that they will be hidden everywhere.

Note: These two buttons will not add a directory separator to the end of the folder names.

You can use the internal command [[Internal Commands#cm_SwitchIgnoreList]] to turn this option on and off, add a button on toolbar or hotkey.

**2.21. Archivers** ^ConfigArchivers

Please see the dedicated [[Archive Handling|Archive handling]] help page about how to use and configure it.

**2.22. Tooltips** ^ConfigTooltips

This section contains the settings for tooltips when the mouse cursor is hovering over a file.

![[pic47.png|Tooltips]]

*Show tooltip for files in the file panel* – enables the ability to use tooltips.

*File types* – contains a list of file groups. Double Commander checks the list from top to bottom until the first match: a file group higher in the list will overlap any file group below.

Buttons:

- *Apply* – will save the settings for the selected file type.
- *Add* – will add a new file type and ask for a name, you may write a description of the file, what it does or what program it opens.
- *Copy* – will copy the selected file type with a new name.
- *Rename* – will prompt to enter a new name for the selected file type.
- *Delete* – will delete the selected file type.

The *Other...* button is a menu:

- *Discard Modifications* – will reset all unsaved changes in the selected file type.
- *Sort Tooltip File Types* – will sort the file types alphabetically (first upper then lower case).
- *Export...* and *Import...* – allow to export tooltips to a DC Tooltip file and import them from such files (in whole or in parts).

Below you can configure the content of the tooltip for the selected file type.

In line *Category mask* put a wildcard mask to match file types (symbol "*" means match any number of characters, symbol "?" means any one character). You may put multiple file types here using a semicolon ";" without spaces. Also you can use search templates (![[btemplate.png|Template...]]), including search with content plugins.

In the *Category hint* field, you can enter any text and use the WDX plugins fields to get information (the ">>" button).

The remaining parameters are general tooltip parameters.

*Tooltip showing mode* – determines what type of tooltips Double Commander will show and how to combine them, if both types:

- Combine DC and system tooltip, DC first (legacy).
- Combine DC and system tooltip, system first.
- Show DC tooltip when possible and system when not.
- Show DC tooltip only.
- Show system tooltip only.

The content of the system tooltip depends on the operating system:

- Windows: File name and the same as in Windows Explorer. If it was not possible to obtain information, then Double Commander will show the same as in Linux and other Unix-like systems.
- Linux and other Unix-like systems: File name, modification date and size.

The first line of the tooltip always contains the file name, and if you did not specify anything in the *Category hint* field, then the DC tooltip will contain only the file name.

*Tooltip hiding delay* – sets the duration of displaying the tooltip: system default, 1 sec, 2 sec, 3 sec, 5 sec, 10 sec, 30 sec, 1 min and never hide (the tooltip will be hidden when you move the mouse cursor to another file or outside the file panel).

In the screenshot at the beginning of the section description, you can see an example of a tooltip with the `textline.wdx` plugin that shows the contents of the selected lines of a text file (in this case, the first, second and third lines), the *Combine DC and system tooltip, system first* mode is selected.

**2.23. File associations** ^ConfigAssociations

This item opens the configuration file associations. All association sets are contained in the file `extassoc.xml`.

Here you can customize file associations and set commands or scripts for chosen file types. Commands will be added to the [[Basic Help#^cm_ContextMenu|context menu]] of files. Double Commander also allows to simply set (or replace) icons for file types, without adding any actions.

![[pic48.png|File associations]]

*File types* – contains a list of extensions. Each group can contain many file extensions, and such a group can be associated with various programs.

*Add* – adds a new group. You should enter a group name.

*Remove* – deletes a group.

*Rename* – allows to set a new name for the group.

*Icon* – you can set the path to an icon for this group. Double Commander supports frequently used image formats, additionally in Windows you can use icons from binary executable files (.exe or .dll; in this case, DC will automatically choose the appropriate icon size from the available ones). You can also specify only the name of the icon without an extension (MIME-type icons are usually used), in this case:

- Windows: Double Commander will use the icon from its own current icon theme.
- Linux and other Unix-like systems: Double Commander will use the icon from the system icon theme, because it has priority. If there is no icon file, the program will use the icon from its own current icon theme.

This is a convenient way, because Double Commander will automatically choose the appropriate icon size from the available ones and will take into account the switching of the icon theme.

*Extensions* – here you can set the extensions (without dot) for the selected group. You can add multiple extensions using a vertical bar "|" (without spaces between them). Special values:

- `file` – any file;
- `folder` – any directory;
- `default` – used when extension specific association does not exists.

*Insert* – adds a new extension to the current position in the list.

*Add* – adds a new extension to the end of the list.

*Remove* – deletes an extension from the group.

*Actions* – here you can set commands for the group.

*Insert* – adds a new action to the current position in the list.

*Add* – adds a new action to the end of the list.

*Remove* – deletes an action from the list.

*Up*, *Down* – moves the action. The actions (if more than one) can be reordered.

*Action name:* – sets type of action. Variants:

- From popup menu
  - Open – action will be run after pressing `Enter` or double click.
  - View – action will be run after pressing `F3`.
  - Edit – action will be run after pressing `F4`.
- Other actions displayed in the file context menu (submenu "Actions").

*Command* – any command from Desktop Environment. Several macros are also available (names are case sensitive!):

- `{!DC-EDITOR}` – call internal editor;
- `{!DC-VIEWER}` – call internal viewer;
- `{!EDITOR}` – call editor (internal or external, depends on the configuration);
- `{!VIEWER}` – call viewer (internal or external, depends on the configuration);
- `{!SHELL}` – run in terminal and stay open at the end.
- `{!TERMSTAYOPEN}` – run in terminal and stay open at the end;
- `{!TERMANDCLOSE}` – run in terminal and request to close it at the end.

"View" actions with the `{!DC-VIEWER}` macro will be taken into account for [[File Viewer#7. Quick view|quick viewing]], other macros and commands will be ignored.

`{!TERMSTAYOPEN}` and `{!TERMANDCLOSE}` have been added for unification and the ability to use the variables [[Variables in Parameters#12. Execute in terminal|%t0 and %t1]], `{!SHELL}` has been kept for backwards compatibility.

As a command, you can use the [[Internal Commands|internal commands]] of Double Commander. The parameters of the internal commands are specified one per line, so you can specify only one here. Also, using the internal command [[Internal Commands#cm_ExecuteScript]], you can run [[Lua Scripting|Lua scripts]], in this case you can get the names of the selected files using internal commands ([[Internal Commands#cm_CopyFullNamesToClip]] or [[Internal Commands#cm_SaveSelectionToFile]]) or the [[Lua Scripting#^dc_expandvar|DC.ExpandVar]] function.

*Parameters* – command parameters including variables:

- any variable from [[Variables in Parameters|"percent" variables]].
- `<?command?>` – runs "command" in the system shell and feeds the output to the command above.

At a minimum, you must specify a file name, usually `%p` or `%p0` for the file under cursor.

*Start path* – command start directory. This directory will become the working directory of the program being launched, and if you do not need to explicitly specify it, then just leave this field empty: in this case, the working directory will be the current directory of the active file panel (regular files) or the system directory for the temporary files (files from archives and WFX plugins). Here we can use the variable [[Variables in Parameters#6. Path of panels|%D]], [[Variables in Parameters#2. Basic parameter variables|%d]] or [[Variables in Parameters#16. Environment variables|environment variables]].

All available actions will be displayed in the "Actions" submenu in the context menu:

![[pic49.png|Context menu]]

**2.23.1. File associations > File associations extra** ^ConfigAssocEx

![[pic79.png|File associations extra]]

*Offer to add selection to file association when not included already* – When accessing file association, offer to add current selected file if not already included in a configured file type. This is a quick way to add an "Open with" action: Double Commander will prompt you to specify a type name and an executable file, everything else will be done automatically.

*Extended context menu* – allows to add some items to the "Actions" submenu:

- *Default context actions (View/Edit)* – Commands for opening a file in the viewer and editor. Built-in tools or external applications will be used (depending on the settings), internal file associations will be ignored.
- Run using macros `{!SHELL}`, `{!TERMANDCLOSE}` and `{!TERMSTAYOPEN}` (see details [[Configuration#^ConfigAssociations|here]]):
  - *Execute via shell*
  - *Execute via terminal and close*
  - *Execute via terminal and stay open*
- *File association configuration* – opens the [[Configuration#^ConfigAssociations|File associations]] settings section.

Below you can choose how the path will be set when adding icons, commands and starting paths:

- With complete absolute path.
- Path relative to [[Variables in Parameters#16. Environment variables|%COMMANDER_PATH%]].
- Relative to the specified path.

Also you can apply the chosen way to the already added paths.

**2.24. Directory Hotlist** ^ConfigDirHotlist

Please see the dedicated [[Directory Hotlist]] help page about how to use and configure it.

**2.24.1. Directory Hotlist > Directory Hotlist Extra** ^ConfigDirHotlistEx

![[pic80.png|Directory Hotlist Extra]]

In this section you can choose how the path will be set the path and target path:

- With complete absolute path.
- Path relative to [[Variables in Parameters#16. Environment variables|%COMMANDER_PATH%]].
- Relative to the specified path.

Also you can apply the chosen way to the already added paths.

Created by Rustem (dok_rust@bk.ru)

English version by Rod J (rodmac_shiels@hotmail.com)

---

[[Indice|← Index]]
