---
title: 1.2. Frequently Asked Questions (FAQ)
source: faq.html
tags: [doublecmd, documentation]
---

# 1.2. Frequently Asked Questions (FAQ)

## Content

- 1. Common questions
  - 1.1. [[FAQ#^whatisit|What is Double Commander?]]
  - 1.2. [[FAQ#^whatsnew|What's new in this version?]]
  - 1.3. [[FAQ#^linux|Is it a Total Commander for Linux?]]
  - 1.4. [[FAQ#^wincmd|What is the difference between this program and my favorite file manager (Total Commander)?]]
  - 1.5. [[FAQ#^link|How can I contact the developers of Double Commander?]]
- 2. Issues related to GNU/Linux
  - 2.1. [[FAQ#^version|Which version do I download?]]
  - 2.2. [[FAQ#^repo|Where is the project repository?]]
  - 2.3. [[FAQ#^plugs|Plugins from Total Commander do not work?!]]
  - 2.4. [[FAQ#^gvfs|Can I get access to network resources like in Nautilus or Thunar?]]
  - 2.5. [[FAQ#^tray|Clicking on the tray icon displays a menu with "Restore" and "Exit" items instead of restoring the window (GTK2 only).]]
  - 2.6. [[FAQ#^systheme|Why does the program's appearance not change or change only partially when switching the system theme? I have to close the program and open it again.]]
- 3. Interface configuration
  - 3.1. [[FAQ#^color|How can I change color settings for the panels?]]
  - 3.2. [[FAQ#^colorbuttons|What are buttons `R` and `All` in the color settings?]]
  - 3.3. [[FAQ#^columns|Some text in a column overwrites another column's text!]]
  - 3.4. [[FAQ#^icons|How to associate my own icons with some file types?]]
  - 3.5. [[FAQ#^splitter|How to create a splitter on the buttons panel?]]
  - 3.6. [[FAQ#^theme|Does DC has other icon themes?]]
  - 3.7. [[FAQ#^cs_size|How to make function keys and address bar bigger?]]
  - 3.8. [[FAQ#^height|File panels: how to change the height of elements (strings) and the intervals between them?]]
- 4. Issues related to control and navigation
  - 4.1. [[FAQ#^cursor_down|Is it possible to automatically move the cursor down one line after selecting using the `Space` key?]]
  - 4.2. [[FAQ#^queue|Is there an ability to create a file operations queue?]]
  - 4.3. [[FAQ#^hotkeys_default|`Ctrl+A` doesn't work, how to enable it?]]
  - 4.4. [[FAQ#^mouse_unmark|When all files are selected in a directory, there is no way to deselect them using a mouse.]]
  - 4.5. [[FAQ#^context_menu_create|How to create my own context menu in this program?]]
  - 4.6. [[FAQ#^context_menu_edit|How to customise the context menu, for example, add the item "Open With"?]]
  - 4.7. [[FAQ#^auto_extract|How to automatically unpack and run file from an open archive? It is inconvenient to use the "Unpack and execute" button in the properties window of the packed file every time.]]
  - 4.8. [[FAQ#^descript_ion|Can the comments (via the descript.ion file) be copied/moved when a file is copied/moved from one directory to another?]]
  - 4.9. [[FAQ#^set_property|In some cases I see warning "Can not set [attributes, date/time, owner/group or permissions] for xxx" when I copy or move files, I want that DC use action "skip"/"skip all" by default. How I can do it?]]
  - 4.10. [[FAQ#^admin_shares|Why doesn't the program show a list of admin shares?]]
  - 4.11. [[FAQ#^hotkey_controls|I assigned the left and right arrows to navigate back and forth through the directory history, but now I can't use them while renaming a file. How to fix it?]]
- 5. Issues related to the built-in viewer (`F3`) and editor (`F4`)
  - 5.1. [[FAQ#^f3_compiz|Editor and browser windows appear in random positions, when Compiz is enabled.]]
  - 5.2. [[FAQ#^f3_font|The font looks strange (horizontal characters overwrite each other and etc) or the selection does not work correctly.]]
  - 5.3. [[FAQ#^f3_jpg|Viewer does not work with a few images, but works with most.]]
  - 5.4. [[FAQ#^f3_hscroll|On some text files lines go beyond the window's edge.]]
  - 5.5. [[FAQ#^f4_colmode|Can you add column editing feature (like in Notepad++, UltraEdit etc)?]]
  - 5.6. [[FAQ#^f34_regutf8|How can I use regular expressions to search in UTF-8?]]
  - 5.7. [[FAQ#^f4_syntax|How to change the syntax highlighting scheme in the internal editor or add new ones?]]
  - 5.8. [[FAQ#^f4_open|How to open a specific file from a manually specified location in the built-in viewer?]]
- 6. Issues related to the file panels
  - 6.1. [[FAQ#^fv_datetime|I didn't find a suitable date format for file panels in the list! How to add my own?]]
  - 6.2. [[FAQ#^fn_ext|I want to see the filenames in the "Name" column with extensions, can I do it?]]
  - 6.3. [[FAQ#^folder_sort|Is it possible to sort folders by clicking on column header ("Date", "Size" and so on)?]]
  - 6.4. [[FAQ#^slinkt|How to see the target objects of symbolic links?]]
  - 6.5. [[FAQ#^parent|How to hide the ".." item for the parent directory in the file list?]]
- 7. Plugins
  - 7.1. [[FAQ#^not_valid|What does the message "This is not a valid plugin!" mean?]]
  - 7.2. [[FAQ#^ftps_reuse|ftp.wfx: I try to use FTPS (FTP+SSL), but I get "522 SSL connection failed: session reuse required".]]
  - 7.3. [[FAQ#^ftp_openssl|ftp.wfx: Does not work with some servers! After connecting, I get errors: "104,Connection reset by peer" and "CSOCK ERROR Connection reset by peer" or "10060,Connection timed out" and "CSOCK ERROR Connection timed out".]]

## 1. Common questions

Q: What is Double Commander? ^whatisit

**A:** Double Commander is a cross-platform, twin-panel file manager. Details see [[What is Double Commander|here]].

Q: What's new in this version? ^whatsnew

**A:** List of changes can be found on the [Wiki page](https://github.com/doublecmd/doublecmd/wiki). But the project is now under development, so later [nightly builds](https://github.com/doublecmd/snapshots/releases) contain many new features and improvements.

Q: Is it a Total Commander for Linux? ^linux

**A:** No, this is another program from other developers. It now supports Windows, GNU/Linux and macOS, also Double Commander is available in the FreeBSD Ports collection.

Q: What is the difference between this program and my favorite file manager (Total Commander)? ^wincmd

**A:** The goal of the project is to create a program close to TC in operation and with maximum compatibility via the plugins and configuration files. However, Double Commander has some important advantages: it's free to use, works with different operating systems, and is open source.

Q: How can I contact the developers of Double Commander? ^link

**A:** The project's [official forum](https://doublecmd.h1n.ru/) or [GitHub](https://github.com/doublecmd/doublecmd).
 Make sure you are using the latest version of the program and it's a good idea to check the development (alpha) version before reporting a bug or requesting a new feature. Also see [#117](https://github.com/doublecmd/doublecmd/issues/117).
 Note: It may be useful to run Double Commander and receive debug messages, see the description of [[Command Line|--debug-log]]. The application also allows to copy the contents of the message window to the clipboard, just press `Ctrl+C`.

## 2. Issues related to GNU/Linux

Q: Which version do I download? ^version

**A:** If you have KDE, LXQt or Fly – download a Qt-build; in other cases (Cinnamon, GNOME, LXDE, MATE or Xfce) a build for GTK toolkit. But this is not strict rule and there are methods available that allow to get a more or less similar look of Qt applications in a GTK environment and vice versa.
 A few words about some details:
 - The GTK2 library do not support Wayland, so Xwayland will be used to run the application in a Wayland session. If you need native Wayland support, then try the Qt version (Qt5 or Qt6).
 - If you use a scaling factor greater than 1 (HiDPI or just a big monitor), then perhaps the Qt version (Qt5 or Qt6) will look more acceptable, check it.

Q: Where is the project repository? ^repo

**A:** Repositories for some GNU/Linux distributions:

- release: [GTK2](https://software.opensuse.org/download.html?project=home:Alexx2000&package=doublecmd-gtk), [Qt5](https://software.opensuse.org/download.html?project=home:Alexx2000&package=doublecmd-qt) or [Qt6](https://software.opensuse.org/download.html?project=home:Alexx2000&package=doublecmd-qt6)
- alpha ("nightly") build: [GTK2](https://software.opensuse.org/download.html?project=home:Alexx2000:doublecmd-svn&package=doublecmd-gtk), [Qt5](https://software.opensuse.org/download.html?project=home:Alexx2000:doublecmd-svn&package=doublecmd-qt) or [Qt6](https://software.opensuse.org/download.html?project=home:Alexx2000:doublecmd-svn&package=doublecmd-qt6)
- beta version (only until the release): [GTK2](https://software.opensuse.org//download.html?project=home:Alexx2000:doublecmd-beta&package=doublecmd-gtk), [Qt5](https://software.opensuse.org//download.html?project=home:Alexx2000:doublecmd-beta&package=doublecmd-qt) or [Qt6](https://software.opensuse.org//download.html?project=home:Alexx2000:doublecmd-beta&package=doublecmd-qt6)

Also portable versions are available (see details [[Basic Help#1.2. Usage|here]]).

Q: Plugins from Total Commander do not work?! ^plugs

**A:** They work, but not all of them. Plugins from TC compiled for Windows can only be used with Windows version of Double Commander. But if the plugins have open source code, you can try to build them for GNU/Linux (or maybe ask the plugin developer to do it :)).
 There are a number of plugins for Linux and cross-platform plugins (see [Wiki](https://github.com/doublecmd/doublecmd/wiki/Plugins), repositories [plugins](https://github.com/doublecmd/plugins), [doublecmd-plugins](https://github.com/j2969719/doublecmd-plugins) and others), as well as several topics on the official forum (for example, [one](https://doublecmd.h1n.ru/viewtopic.php?f=8&t=4106), [two](https://doublecmd.h1n.ru/viewtopic.php?f=8&t=3333)).

Q: Can I get access to network resources like in Nautilus or Thunar? ^gvfs

**A:** Yes, DC can use GVfs. GVfs supports many protocols: NFS, SMB, FTP, SFTP, WebDAV, MTP, mobile phones (Windows, Android, Apple), media players and other.

First, packages `gvfs`, `gvfs-backends` and `gvfs-fuse` should be installed. Keep in mind that some distributions have not packages `gvfs-backends` and `gvfs-fuse`, because they are part of package `gvfs`, or it can be several packages with names `gvfs-backends-*` or `gvfs-*`.

Now insert GVfs path in the address bar: click by right mouse button at address bar to edit it (or call internal command `cm_EditPath`).

For example, access to

- FTP: `ftp://ftpuser@ftpserver`
- SMB: `smb://servername/sharename/`
- WebDAV: `davs://servername`

For a list of supported protocols, see the GVfs documentation.

Well, for access to FTP (for SSH+SCP too) you can use the [[Pre-installed Plugins#^ftp-wfx|FTP plugin]].

Q: Clicking on the tray icon displays a menu with "Restore" and "Exit" items instead of restoring the window (GTK2 only). ^tray

**A:** Add a library of general system tray support: for example, package `libappindicator1` in Debian/Ubuntu or `libappindicator-gtk2` in Arch Linux.

Q: Why does the program's appearance not change or change only partially when switching the system theme? I have to close the program and open it again. ^systheme

**A:** GTK2 version? This is a feature of Lazarus, in this case, it does not update controls colors under GTK2.

## 3. Interface configuration

Q: How can I change color settings for the panels? ^color

**A:** To change the color, you must go to Configurations > Options... > Colors > File panels. These are global settings for both panels and can be overridden, see Configurations > Options... > Files views > Columns > Custom columns.

Q: What are buttons `R` and `All` in the color settings? ^colorbuttons

**A:** They are as follows:

- `R` – restore color to the default.
- `All` – apply selected color to all columns.

Q: Some text in a column overwrites another column's text! ^columns

**A:** Configurations > Options... > Files views > Columns, set checkbox "Cut text to column width".

Q: How to associate my own icons with some file types? ^icons

**A:** You should do the following: Configurations > Options... > [[Configuration#^ConfigAssociations|File associations]].

Q: How to create a splitter on the buttons panel? ^splitter

**A:** Add a button from the category [[Toolbar#5.1. Description of elements - Separator|separator]].

Q: Does DC has other icon themes? ^theme

**A:** Now we know only one small theme [DoubleMac](https://doublecmd.h1n.ru/viewtopic.php?f=5&t=3658), but the installation instruction is outdated (see below).
 You can make icon theme yourself, it's easy (we will use the name "MyDCTheme" as an example).

*How to make:*
 - open DC folder and see directory structure of "pixmaps/dctheme";
 - make copy of "dctheme" with name "mydctheme";
 - open "mydctheme/index.theme" and change the theme name: replace "Name=DCTheme" on "Name=MyDCTheme";
 - now replace icons.

*Notes:*
 1. Don't use the default icon replacement! Your icons will be replaced after DC update.
 2. If you want to keep some existing default icons then just delete them in "mydctheme" and DC will use them from default theme.
 3. Some nonstandard icon sizes (such as 40x40, 60x60 and so one) uses for HiDPI monitors.
 4. Also see [[doublecmd.xml Settings|<CustomIcons>]].

*How to install:*

1. Portable version
 Copy (or move) your "mydctheme" folder to the "pixmaps" folder near `doublecmd.exe`, restart DC, go to "Configuration" in the main menu > Options... > Icons > Icon theme, choose your theme and restart DC again.

2. Installed version
 Go to "Configuration" in the main menu > Options... > Configuration > Directories > Icon themes:, here you will see the list of possible directories.
 Don't use */usr/share/doublecmd/pixmaps*, *C:\Program Files\Double Commander\pixmaps* or other system directory: this requires root/admin privileges, also this would be a intervention to the packages manager's work in Linux or DC installer for Windows. DC usually suggests the following additional path (besides the "pixmaps" folder near `doublecmd.exe`):

- Windows XP: *C:\Documents and Settings\<UserName>\Local Settings\doublecmd\pixmaps*
- Windows Vista/7+: *C:\Users\<UserName>\AppData\Local\doublecmd\pixmaps*
- Unix-like OS: */home/<UserName>/.local/share/doublecmd/pixmaps*

If the directory doesn't exist, create it.
 Now restart DC, go to "Configuration" in the main menu > Options... > Icons > Icon theme, choose your theme and restart DC again.

Q: How to make function keys and address bar bigger? ^cs_size

**A:** The size depends on the font size, three ways exists:

1. Simple and fast: you can use `Ctrl`+mouse wheel, it works for the following interface elements or part of DC:
 - file list in left and right panels;
 - current directory (address) bar;
 - function key buttons bar;
 - TreeView menu;
 - search results in find files dialog;
 - internal editor;
 - internal viewer (if viewer shows text then this action will change font size, if image then action will work as zoom in/zoom out commands).

2. Go to "Configuration" in the main menu > Options... > Fonts.
 Note: All possible are available in version 1.0.0+ only, for 0.9.x and below additionally see the third item.

3. Close DC > open `doublecmd.xml` > find tag `<Fonts></Fonts>` and change `<Size>` of the interface element manually.

Q: File panels: how to change the height of elements (strings) and the intervals between them? ^height

**A:** The view depends on the following parameters:

- Configuration > Options... > Fonts > Main font
- Configuration > Options... > Icons > Icon size > File panel
- [[doublecmd.xml Settings|<ExtraLineSpan>]] (from `<FilesViews>`)

## 4. Issues related to control and navigation

Q: Is it possible to automatically move the cursor down one line after selecting using the `Space` key? ^cursor_down

**A:** You should do the following: Configurations > Options... > File views > When selecting file with spacebar, move down to next file (as with insert).

Q: Is there an ability to create a file operations queue? ^queue

**A:** A file operations queue was implemented in version 0.4.6 alpha, and was added to the next stable release.

Q: `Ctrl+A` doesn't work, how to enable it? ^hotkeys_default

**A:** You should do the following: Configurations > Options... > Keys > Hot keys > In the category "Main", scroll to see command `cm_MarkMarkAll` and set `Ctrl+A` shortcut key for it.

Q: When all files are selected in a directory, there is no way to deselect them using a mouse. ^mouse_unmark

**A:** Several ways:

- Use the ".." item at the beginning of the file list (but if the list of files is long, it will be necessary to scroll it for this).
- Use the main menu: Mark > Unselect All.
- Add the "Unselect All" button (internal command `cm_MarkUnmarkAll`) on the toolbar.
- Go to "Configuration" in the main menu > Options... > Mouse > Selection by mouse > enable "By clicking on icon": the first click will unmark one file, now click on his name. (How to use in thumbnail view, see the [[Configuration#^ConfigMouse|description]] of this parameter.)

Q: How to create my own context menu in this program? ^context_menu_create

**A:** Add button to the toolbar of the category "menu". See [[Toolbar#5.4. Description of elements - Menu|this section]] for an example.

Q: How to customize the context menu, for example, add the item "Open With"? ^context_menu_edit

**A:** This can been incorporated into Double Commander; however, it's easy to add a command to the "Actions" submenu of the context menu. Here is an example of how to open any directory with root privileges:

1. Under File Types, click Add, then enter, e.g. `Dir` in the popup.
2. Under Extensions, click Add, and enter, e.g. `folder` in the popup.
3. Under Actions, click Add, then in the Action: edit line below, enter the action desired, e.g. `Open as root`
4. In the Command edit line, enter the desired command: eg. `pkexec doublecmd %p`
5. After this just right click on any folder, choose "Open as root" and enter root's password. :)

Q: How to automatically unpack and run file from an open archive? It is inconvenient to use the "Unpack and execute" button in the properties window of the packed file every time. ^auto_extract

**A:** See description of [[doublecmd.xml Settings|<AutoExtractOpenMask>]].

Q: Can the comments (via the descript.ion file) be copied/moved when a file is copied/moved from one directory to another? ^descript_ion

**A:** Yes, it is possible: go to Configurations > Options > File operations and enable "Process comments with files/folders".

Q: In some cases I see warning "Can not set [attributes, date/time, owner/group or permissions] for xxx" when I copy or move files, I want that DC use action "skip"/"skip all" by default. How I can do it? ^set_property

**A:** Run a copy or move operation and change the value of the [[Copying and Moving Files#1. Copy/move dialog window|When cannot set property]] option to "Ignore". The "Save these options as default" button will allow to use this value for subsequent operations.

Q: Why doesn't the program show a list of admin shares? ^admin_shares

**A:** Administrative shares are hidden network shares, make sure that you have enabled the display of hidden files and folders (use the [[Configuration#^ConfigViewEx|program settings]] or the corresponding item in the [[Basic Help#2.1.7. "Show"|Show]] menu).

Q: I assigned the left and right arrows to navigate back and forth through the directory history, but now I can't use them while renaming a file. How to fix it? ^hotkey_controls

**A:** When assigning a hot key, Double Commander allows to limit the scope of the keyboard shortcut, see [[Configuration#^ConfigHotKeys|Only for these controls]].
In this case, you need to enable the "Files Panel".

## 5. Issues related to the built-in viewer ( F3 ) and editor ( F4 )

Q: Editor and browser windows appear in random positions, when Compiz is enabled. ^f3_compiz

**A:** Edit Compiz settings: place windows > windows with fixed positions and window rules > fixed size windows.

```
(class=Doublecmd) & (title=/)
```

Q: The font looks strange (horizontal characters overwrite each other and etc) or the selection does not work correctly. ^f3_font

**A:** You should use monospace fonts in the viewer and editor.

Note: "Monospace" is a font alias and the value may not be from the monospace font family. If you have a problem, try specifying a real monospace font in the Double Commander settings.

Q: Viewer does not work with a few images, but works with most. ^f3_jpg

**A:** A component used to view the images did not support some JPEG files.

Q: On some text files lines go beyond the window's edge. ^f3_hscroll

**A:** Enable "Wrap text" option in the viewer (in the "View" menu). Internal editor does not support wrap lines.

Q: Can you add column editing feature (like in Notepad++, UltraEdit etc)? ^f4_colmode

**A:** Internal editor supports column and line selection modes and multi-carets, see keyboard shortcuts [[Keyboard Layout#9. Internal Editor|here]].

Q: How can I use regular expressions to search in UTF-8? ^f34_regutf8

**A:** This feature has been added to version 1.0.0. Needs PCRE2 library with support 8-bit code units and Unicode support enabled (usually enabled by default):

- Windows: needs `libpcre2-8.dll` (by default, the Double Commander distribution contains this DLL).
- Linux: needs `libpcre2-8.so.0`. For example, package `libpcre2-8-0` in Debian/Ubuntu or `pcre2` in Arch Linux.
- macOS: needs `libpcre2-8.dylib`.

Q: How to change the syntax highlighting scheme in the internal editor or add new ones? ^f4_syntax

**A:** DC uses two components:

1. *SynEdit* with built-in syntax highlighters. If you want to change any highlighter, you should change the DC or Lazarus source code. But you can easily change the colors used and the file extension lists: go to "Configuration" in the main menu > Options... > Tools > Editor > Highlighters. Do not forget to save customizations for each file type.

2. *SynUniHighlighter* for custom syntax highlighting schemes (.hgl) and you can try to find or create this files yourself (see below).

This files are usual XML-based files, you can open them in a text editor and read/change. In the beginning of this files is the `<General>` tag (inside `<Info>`):

1) Old format: `<General>` has tags
 - `<Name>`: name for the *Syntax highlight* menu;
 - `<FileTypeName>`: list of supported file extensions.

2) New format: `<General>` has attributes
 - `Name`: name for the *Syntax highlight* menu;
 - `Extensions`: list of supported file extensions.

(DC supports both formats.)

*How to create or edit:*

Use UniHighlighter Editor or HglEditor ([download](https://sourceforge.net/projects/doublecmd/files/Double%20Commander%20Addons/)). Both programs were written for Windows, but you can use Wine. HglEditor will save HGL-file in the new format.
 Two packs of various highlighters are also available.
 In the [[Configuration#^ConfigToolsEditorHL|Tools > Editor > Highlighters]] section, you can change the text and background colors and font style.

*How to add:*

1) Portable version
 Copy (or move) your HGL-file(s) to the "highlighters" folder near `doublecmd.exe` and restart DC.

2) Installed version
 Go to "Configuration" in the main menu > Options... > Configuration > Directories > Highlight:, here you will see the list of possible directories.
 Don't use */usr/share/doublecmd/highlighters*, *C:\Program Files\Double Commander\highlighters* or other system directory: this requires root/admin privileges, also this would be a intervention to the packages manager's work in Linux or DC installer for Windows. DC usually suggests the following additional path (besides the "highlighters" folder near `doublecmd.exe`):

- Windows XP: *C:\Documents and Settings\<UserName>\Local Settings\doublecmd\highlighters*
- Windows Vista/7+: *C:\Users\<UserName>\AppData\Local\doublecmd\highlighters*
- Unix-like OS: */home/<UserName>/.local/share/doublecmd/highlighters*

If the directory doesn't exist, create it. Now restart DC.

*Additional features:*

1) *Other* submenu

Additional *Syntax highlight* menu item: if menu is too long then you can move some items to the *Other* submenu. Just add new attribute `Other` and value 1 to the `<General>` tag and restart DC.
 For example, before
 `<General Name="AutoIt v3*" Extensions="AU3"/>`
 and after
 `<General Name="AutoIt v3*" Extensions="AU3" Other="1"/>`

Q: How to open a specific file from a manually specified location in the built-in viewer? ^f4_open

**A:** Add a button with an external command to the [[Toolbar|toolbar]], specify the [[Configuration#^ConfigAssociations|{!DC-VIEWER}]] macro as the command, and add the full name of the desired file in the parameters field.

## 6. Issues related to the file panels

Q: I didn't find a suitable date format for file panels in the list! How to add my own? ^fv_datetime

**A:** Date and time format is easy configurable: go to Configurations > Options > Files views > Formatting > Date and time format and use [[Configuration#^dt_format|this table]].

Q: I want to see the filenames in the "Name" column with extensions, can I do it? ^fn_ext

**A:** Yes, it's possible. Go to "Configuration" in the main menu > Options... > Files views > Columns > Custom columns, now create a new column set or change existing default set: by default, DC uses `GETFILENAMENOEXT` field for name, use `GETFILENAME` instead.

Q: Is it possible to sort folders by clicking on column header ("Date", "Size" and so on)? ^folder_sort

**A:** Yes, you can enable this feature: go to "Configuration" in the main menu > Options... > Files views > Sorting > Sorting directories and use "sort like files and show first" or "sort like files".

Q: How to see the target objects of symbolic links? ^slinkt

**A:** In addition to the file properties dialog, you can use `GETFILELINKTO` in a [[Configuration#^ConfigColumns|set of columns]] or a [[Configuration#^ConfigTooltips|tooltip]]. In the last case, you should create a search template and specify `l+` in the attributes.
 Also you can [[Lua Scripting|use Lua]] and write in the log window.

Q: How to hide the ".." item for the parent directory in the file list? ^parent

**A:** Use the [[Configuration#^ConfigIgnore|Ignore list]] in the program settings (a less global way is also possible, for example, `///Search result/..` will hide this item only in search results).

## 7. Plugins

Q: What does the message "This is not a valid plugin!" mean? ^not_valid

**A:** This usually means a problem with dependencies: not all required libraries are available in your system. If there are no details in the description of the plugin, could not contact the author or find a solution using search engines, then try the following:

- Windows: FileInfo or PEViewer plugin, utilities such as DLL Export Viewer or Dependency Walker.
- Linux: use terminal and command `ldd` (the easiest way, `ldd pluginname | grep "not found"`), GNU Binutils or AnyELF plugin.

If this is a WDX plugin written in Lua:

1. The Lua library is not available: see [[Lua Scripting#2. DLL required|DLL required]].

2. The script requires an additional module: see the description of the script or contact the author.

3. Error in the script. For debugging, you can use Lua in a terminal or advanced code editor/IDE (for example, ZeroBrane Studio).
 If you use the [[Lua Scripting#3. Double Commander functions libraries|Double Commander functions]]: create a button with internal command [[Internal Commands#cm_ExecuteScript]] and use available functions (`DC.LogWrite`, `Dialogs.MessageBox`, `Clipbrd.SetAsText` or save the results to a file).

Q: ftp.wfx: I try to use FTPS (FTP+SSL), but I get "522 SSL connection failed: session reuse required". ^ftps_reuse

**A:** This server requires session reuse support and the FTP plugin supports it, but requires a library that supports SSL and TLS protocols (see the [[Pre-installed Plugins#^ftp-wfx|description]] of the plugin).

Q: ftp.wfx: Does not work with some servers! After connecting, I get errors: "104,Connection reset by peer" and "CSOCK ERROR Connection reset by peer" or "10060,Connection timed out" and "CSOCK ERROR Connection timed out". ^ftp_openssl

**A:** Requires a library that supports SSL and TLS protocols (see the [[Pre-installed Plugins#^ftp-wfx|description]] of the plugin).

---

[[Indice|← Index]]
