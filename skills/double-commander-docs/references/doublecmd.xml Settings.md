---
title: 2.17. Settings in doublecmd.xml
source: configxml.html
tags: [doublecmd, documentation]
---

# 2.17. Settings in doublecmd.xml

## Content

- 1. [[doublecmd.xml Settings#1. Presentation|Presentation]]
- 2. [[doublecmd.xml Settings#2. Location|Location]]
- 3. [[doublecmd.xml Settings#3. Options to change manually|Options to change manually]]
- 4. [[doublecmd.xml Settings#4. Index|Index]]

## 1. Presentation

Main settings of Double Commander are saved/restored to/from an [XML](https://en.wikipedia.org/wiki/XML) file named `doublecmd.xml`.

## 2. Location

The location of this `doublecmd.xml` file may be in different places:

- It may be configured to be in the user home directory.
- It may be configured to be in the program directory itself, which is commonly the case when used in a portable context.
- We may define its location via a command line parameter when launching the application.

We follow [[Command Line|this link]] if we want to specify it by with the command line paramter `--config-dir`.

Other than that, we do Configuration > Options... > select in the tree ![[optionconfiguration.png|Double Commander]] > set the option *Location of configuration files*.

![[configlocation.png|Location of configuration file]]

Another way to quickly find out where is located the `doublecmd.xml` the current instance of Double Commander is using is by accessing the [[Directory Hotlist]]. At the end of it there is a sub section called "Special Dirs". Then we select "Go to Double Commander special path" and then "%DC_CONFIG_PATH%". We will find there the `doublecmd.xml` that application is currently using.

## 3. Options to change manually

The large majority of possible settings in Double Commander may be set via the application itself through the various option categories.

We simply click from the main menu bar Configuration > Options and the various settings we'll configured there will be saved to the `doublecmd.xml` file when we close the application. Then, they will be restored on the next usage of the application.

So generally, we don't have to manually edit the content of the configuration file.

But there are some very rare specific settings that required to be edited manually from the configuration file if we want to tweak the application.

**WARNING:** We will not edit that file WHILE Double Commander is running! Not only because anyway their values are read only when we're starting the application, but also because if we edited the file while DC is running, when we'll close the application the values we would have wrote will be overwritten by the application re-saving its current context for next session. If we need to edit the `doublecmd.xml` file, we need to make sure we close Double Commander, then we edit file, and then we re-launch the application.
 There is an alternative solution, see more details [[Configuration#^ConfigDC|here]] (but to apply changes to some options, you may still need to restart the application).

The following table gives us these rare specific settings that we need to manually edit the file if we need to change them.

<table>
<tr class="rowcategorytitle"><th colspan="2">Setting required to be changed manually if necessary</th></tr>
<tr class="rowsubtitle"><th class="namecolumn">Tag</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <AutoRefresh>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="Mode"></a><Mode></div></td>
<td class="hintcell">
              The ability to delete watched directories.<br>A "watched directory" is a directory that Double Commander has a kind of hook on it so it can monitor any modification in it.<br>This way, it can refresh the displayable content of it if it's content changed.<br>
              This setting allows to control how Double Commander will react if we attempt to delete one of these "watched directory" currently displayed in a panel, even in a non-activated tab.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">0</td>
<td class="innerdescdesccell">Prevents deleting watched directories.</td>
</tr>
<tr>
<td class="innerdescvaluecell">1</td>
<td class="innerdescdesccell">Does not prevent deleting watched directories (default).</td>
</tr>
<tr>
<td class="innerdescvaluecell">2</td>
<td class="innerdescdesccell">Watch whole drives instead of single directories to omit problems with deleting watched directories.</td>
</tr>
</table>
<i>Example:</i> <code><Mode>1</Mode></code>
</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Behaviours>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ActiveRight"></a><ActiveRight></div></td>
<td class="hintcell">
              The right panel will be active when Double Commander starts.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">True</td>
<td class="innerdescdesccell">Right panel</td>
</tr>
<tr>
<td class="innerdescvaluecell">False</td>
<td class="innerdescdesccell">Left panel (default)</td>
</tr>
</table>
<i>Example:</i> <code><ActiveRight>True</ActiveRight></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ConfirmQuit"></a><ConfirmQuit></div></td>
<td class="hintcell">Confirm closing Double Commander (<code>True</code>) or not (<code>False</code>). <code>False</code> by default.</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Colors>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="gBorderFrameWidth"></a><gBorderFrameWidth></div></td>
<td class="hintcell">
              We may configure DC so it will draw a rectangle around the active entry as we we cycle through them in a panel.<br>
<code><gBorderFrameWidth></code> allows us to configure the width of the lines used to draw a rectangle around the current active entry.<br>
              To view that rectangle, we should go in Configuration > Options... > Colors > File panels and check the option <i>Use frame cursor</i>.<br>
<i>Example:</i> <code><gBorderFrameWidth>1</gBorderFrameWidth></code>
</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Editor>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="FindWordAtCursor"></a><FindWordAtCursor></div></td>
<td class="hintcell">Internal editor and differ tool: if nothing is selected, the search and replace dialog will use the word under the cursor (<code>True</code>) or text from the search history (<code>False</code>). <code>True</code> by default.</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <FileOperations>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="AutoExtractOpenMask"></a><AutoExtractOpenMask></div></td>
<td class="hintcell">
               Suppose we've "entered" into a compressed file and browsing its content in the active panel. The files with the specified extension of this setting will be automatically unpacked from the archive when we press <kbd>Enter</kbd> or double-click on them instead of showing the properties window.<br>
<i>Example:</i> <code><AutoExtractOpenMask>*.txt;*.mp3;*.mp4</AutoExtractOpenMask></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="DefaultDropEffect"></a><DefaultDropEffect></div></td>
<td class="hintcell">The default action when <a href="Basic Help.md#draganddrop">drag & drop files</a> with the mouse: copying (<code>True</code>) or moving (<code>False</code>) files. <code>True</code> by default.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="LongNameAlert"></a><LongNameAlert></div></td>
<td class="hintcell">Warn if target path is longer than maximum length for a path (some programs will not be able to access a file/directory with such a long name). In Windows this value (MAX_PATH) is defined as 260 characters. <code>True</code> by default.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="NtfsHourTimeDelay"></a><NtfsHourTimeDelay></div></td>
<td class="hintcell">
              Ignore time difference of exactly one hour between entries when comparing their date and time.<br>
              This takes place when using internal commands <a href="Internal Commands.md#cm_CompareDirectories">cm_CompareDirectories</a> or <a href="Internal Commands.md#cm_SyncDirs">cm_SyncDirs</a>.<br>
              It is useful when comparing items located on a NTFS partition to another one not on such partition.<br>
              Since the <a href="https://support.microsoft.com/en-us/help/129574/time-stamp-changes-with-daylight-savings" target="_blank">time stamp of a file changes on a NTFS partition</a> when daylight savings period occurs and not when the same exact file is from a FAT32, we want the two files to be consider identical even if we visibly see a one hour difference between the two.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">True</td>
<td class="innerdescdesccell">Enable, a difference of exactly one hour will be considered the same time</td>
</tr>
<tr>
<td class="innerdescvaluecell">False</td>
<td class="innerdescdesccell">Disable (default)</td>
</tr>
</table>
<i>Example:</i> <code><NtfsHourTimeDelay>True</NtfsHourTimeDelay></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="Sounds"></a><Sounds></div></td>
<td class="hintcell">
              Enables sound notifications when file operations are finished. Possible contents of the <code><Sounds></code> tag in full:<br>
<pre>
<Sounds Duration="-1">
  <Copy>C:\Windows\Media\Alarm01.wav</Copy>
  <Move>C:\Windows\Media\Alarm01.wav</Move>
  <Wipe>C:\Windows\Media\Alarm01.wav</Wipe>
  <Delete>C:\Windows\Media\Alarm01.wav</Delete>
  <Split>C:\Windows\Media\Alarm01.wav</Split>
  <Combine>C:\Windows\Media\Alarm01.wav</Combine>
</Sounds></pre>
<code>Duration</code> is the minimum time (in seconds) that a file operation should last. Additional values: 0 – always on, -1 disables sound notifications.<br>
              File operations: copy, move, wipe, delete files, split file and combine files. If a sound notification is not needed for some operation, just remove (or do not add) the corresponding line. <a href="Variables in Parameters.md#envvariables">Environment variables</a> are supported.<br>
              Supported audio formats:<br>
              - Windows (the <tt>sndPlaySoundW</tt> function from the Windows API): .wav.<br>
              - macOS (the Core Audio API): .aac, .adts, .ac3, .caf, .mp3, .m4a and .mp4 (with AAC or ALAC), .wav.<br>
              - Linux and other Unix-like systems: Double Commander can use the GStreamer library (primarily, <tt>libgstreamer-1.0.so.0</tt>) or the SDL2 library (<tt>libSDL2-2.0.so.0</tt>). GStreamer supports most popular audio formats, with SDL2 we can use only .wav. In Haiku, only SDL2 can be used.
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <FileOperations><Options>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="CopyAttributes"></a><CopyAttributes></div></td>
<td class="hintcell">
              Windows: if <code>True</code>, the attributes of the source file will be copied when copying/moving files; if <code>False</code>, the attributes of the source file will also be copied and Double Commander will set the "archive" attribute.<br>
              Linux and others: use the <span class="italic">Copy attributes</span> option in the <a href="Copying and Moving Files.md">copy/move dialog window</a>.<br>
<code>True</code> by default.
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="CopyTime"></a><CopyTime></div></td>
<td class="hintcell">
              Windows: if <code>True</code>, the timestamps of the source file will be copied (creation date, modification date, last access date) when copying/moving files, otherwise, only the modification date will be copied and the current date will be used for others.<br>
              Linux and others: use the <span class="italic">Copy date/time</span> option in the <a href="Copying and Moving Files.md">copy/move dialog window</a>.<br>
<code>True</code> by default.
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="CopyXattributes"></a><CopyXattributes></div></td>
<td class="hintcell">
              Copy filesystem extended attributes when copying/moving files or not.<br>
              Windows: if <code>True</code>, compressed and encrypted attributes will also be copied.<br>
              Linux and other Unix-like systems: if <code>True</code>, Double Commander will copy filesystem extended attributes (xattr, i.e. the named attributes).<br>
<code>True</code> by default.
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <FilesViews>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ExtraLineSpanF"></a><ExtraLineSpan></div></td>
<td class="hintcell">
              This setting allows to add some extra pixels to the height allowed for each element displayed in the file panels. The value is interpreted directly in pixels.<br>
              Default value is 2.<br>
<i>Example:</i> <code><ExtraLineSpan>2</ExtraLineSpan></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="FolderPrePostfix"></a><FolderPrefix> <small>and</small> <FolderPostfix></div></td>
<td class="hintcell">
              By default DC shows square brackets around directory names (it's optional parameter in Files views > Files views extra), but we can use any symbols instead them.<br>
              Note: In XML some special symbols are reserved as part of markup and we can not use them as is. There are five predefined entities: <code><</code> should write as <code>&lt;</code>, <code>></code> as <code>&gt;</code>, <code>&</code> as <code>&amp;</code>, <code>'</code> as <code>&apos;</code> and <code>"</code> as <code>&quot;</code>.
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="RenameConfirmMouse"></a><RenameConfirmMouse></div></td>
<td class="hintcell">
              This option changes the mouse click action when renaming a file under the cursor: if <code>True</code>, the mouse click outside the name edit field will confirm renaming the file (as in Windows Explorer), otherwise, the mouse click will work the same as the <kbd>Esc</kbd> key.<br>
<code>False</code> by default.<br>
              In both cases, we can still use the button to the right of the edit field to confirm the operation.
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <FilesViews><ColumnsView>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="AutoSaveWidth"></a><AutoSaveWidth></div></td>
<td class="hintcell">
              When we manually change the column width with the mouse help, by default DC changes it for both panels and saves a new value for the next launches.<br>
              If we want to disable this behavior and use new value only in the current session, we should replace <code>True</code> with <code>False</code>, i.e. use <code><AutoSaveWidth>False</AutoSaveWidth></code>.
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="LongInStatus"></a><LongInStatus></div></td>
<td class="hintcell">If the columns view is set and there are no selected files, the status bar displays the file name under the cursor (<code>True</code>) or the number of files (<code>False</code>, by default).<br>
              If <code>True</code>, the status bar will also show the number of files when the cursor is on the ".." item. For links, target objects will additionally be displayed.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="TitleStyle"></a><TitleStyle></div></td>
<td class="hintcell">
              Changes the look of tabstop headers bar.<br>Default value depends on your OS.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">0</td>
<td class="innerdescdesccell"><b>tsLazarus</b>: The default Lazarus's look.</td>
</tr>
<tr>
<td class="innerdescvaluecell">1</td>
<td class="innerdescdesccell"><b>tsStandard</b>: A more contrasted look, like Delphi grids.</td>
</tr>
<tr>
<td class="innerdescvaluecell">2</td>
<td class="innerdescdesccell"><b>tsNative</b>: Tries to set a look that is in concordance with current widgetset theme.</td>
</tr>
</table>
<i>Example:</i> <code><TitleStyle>2</TitleStyle></code>
</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from many tags <Fonts>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="Quality"></a><Quality></div></td>
<td class="hintcell">
              Determine what type of <a href="https://en.wikipedia.org/wiki/Font_rasterization" target="_blank">font rasterization</a> that will be used. In other words, it determine the font quality.<br>
              There are many tags where it's applicable individually.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">0</td>
<td class="innerdescdesccell"><b>Default</b>: The quality is determined by the system settings (default).</td>
</tr>
<tr>
<td class="innerdescvaluecell">1</td>
<td class="innerdescdesccell"><b>Draft</b>: For raster fonts, scaling is enabled; the font size can be increased but the quality may be lower.<br>Also the font supports Bold, Italic, Underline or Strikeout if necessary.<br>The quality is less important than when Proof is used.</td>
</tr>
<tr>
<td class="innerdescvaluecell">2</td>
<td class="innerdescdesccell"><b>Proof</b>: The quality of the characters is important, so for the raster fonts, scaling is disabled and the font closest in size is chosen.</td>
</tr>
<tr>
<td class="innerdescvaluecell">3</td>
<td class="innerdescdesccell"><b>NonAntialiased</b>: The font is never antialiased.</td>
</tr>
<tr>
<td class="innerdescvaluecell">4</td>
<td class="innerdescdesccell"><b>Antialiased</b>: The font is always antialiased if it supports it.<br>The size of the font cannot be too small or too large.</td>
</tr>
<tr>
<td class="innerdescvaluecell">5</td>
<td class="innerdescdesccell"><b>ClearType</b>: The font is rendered using the <a href="https://en.wikipedia.org/wiki/ClearType" target="_blank">ClearType</a> anti-aliasing method.</td>
</tr>
<tr>
<td class="innerdescvaluecell">6</td>
<td class="innerdescdesccell"><b>ClearTypeNatural</b>: The font is rendered using the Natural ClearType antialiasing method.</td>
</tr>
</table>
<i>Example:</i> <code><Quality>1</Quality></code>
</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <History>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="Count"></a>Attribute <i>Count</i><br><small>from <History><DirHistory></small></div></td>
<td class="hintcell">
              The <code>Count</code> attribute allows to specify the number of entries from the list of visited directories that will be displayed in the popup menu (the <a href="Internal Commands.md#cm_DirHistory">cm_DirHistory</a> command). Default value is 30.<br>
              When using the Tree View Menu, the attribute value will be ignored.
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Icons>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="CustomIcons"></a><CustomIcons></div></td>
<td class="hintcell">
              This option will help to determine if the icons used for drives, folders or archives will be the default ones from the system or if it will be custom ones that we may set ourselves.<br>
              The <code>CustomIcons</code> option will be set to a single number representing the sum of the numbers from the following table depending on what are our preferences:<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Element</th>
<th class="innerdescheader">From system</th>
<th class="innerdescheader">Custom</th>
</tr>
<tr>
<td class="innerdescvaluecell">Drives</td>
<td class="innerdescdesccell">0</td>
<td class="innerdescdesccell">1 (Windows only)</td>
</tr>
<tr>
<td class="innerdescvaluecell">Folders</td>
<td class="innerdescdesccell">0</td>
<td class="innerdescdesccell">2 (all except Haiku)</td>
</tr>
<tr>
<td class="innerdescvaluecell">Archives</td>
<td class="innerdescdesccell">0</td>
<td class="innerdescdesccell">4 (Windows, Linux and FreeBSD)</td>
</tr>
</table>
<br>
<i>
                If we want...<br>
                ...everything from the system: 0 + 0 + 0= 0 so <code><CustomIcons>0</CustomIcons></code><br>
                ...everything custom: 1 + 2 + 4 = 7 so <code><CustomIcons>7</CustomIcons></code><br>
                ...drive custom, other system: 1 + 0 + 0 = 1 so <code><CustomIcons>1</CustomIcons></code><br>
                etc...
              </i>
<br><br>
              If we wish to use custom icons, here is the location for each items:<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Element</th>
<th class="innerdescheader">Location</th>
</tr>
<tr>
<td class="innerdescvaluecell">Drives</td>
<td class="innerdescdesccell">%commander_path%\pixmaps\theme\XxX\devices\</td>
</tr>
<tr>
<td class="innerdescvaluecell">Folders</td>
<td class="innerdescdesccell">%commander_path%\pixmaps\theme\XxX\places\folder.png</td>
</tr>
<tr>
<td class="innerdescvaluecell">Archives</td>
<td class="innerdescdesccell"><small>%commander_path%\pixmaps\theme\XxX\mimetypes\package-x-generic.png</small></td>
</tr>
</table>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="DiskAlpha"></a><DiskAlpha></div></td>
<td class="hintcell">
              Option to set the transparency level of unmounted drive icons.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">1 to 99</td>
<td class="innerdescdesccell">Valid transparency level (default is 50).</td>
</tr>
<tr>
<td class="innerdescvaluecell">0 or 100</td>
<td class="innerdescdesccell">Disables function.</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ToolSize"></a><ToolSize></div></td>
<td class="hintcell">Size of toolbar icons in the internal editor, viewer and differ tool, supported values: 16, 24 or 32.</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Layout>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ShowColonAfterDrive"></a><ShowColonAfterDrive></div></td>
<td class="hintcell">Windows only: show colon after letters of disks in the <a href="Basic Help.md#iface_drive_pane">drives button bar</a> and in the <a href="Basic Help.md#iface_drive_btn">drives list</a>. <code>False</code> by default.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="UppercaseDriveLetter"></a><UppercaseDriveLetter></div></td>
<td class="hintcell">
              Windows only: use uppercase letters in the <a href="Basic Help.md#iface_drive_pane">drives button bar</a> and in the <a href="Basic Help.md#iface_drive_btn">drives list</a>. <code>False</code> by default.<br>
              Note: This option does not change drive letters in previously saved history and settings (favorites, buttons and so on).
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Miscellaneous>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="DecimalSeparator"></a><DecimalSeparator></div></td>
<td class="hintcell">The option allows to specify the preferred decimal separator character (i.e. separator for integer and fractional parts of a number) instead of the value from your regional settings. We can specify any character from the ASCII table with a code from U+0000 to U+007F (the use of printable characters is implied, i.e. from U+0020 to U+007E).</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="DoubleClickEditPath"></a><DoubleClickEditPath></div></td>
<td class="hintcell">The option allows to choose the action of double-clicking on the the <a href="Basic Help.md#iface_dir">current directory bar</a>: show directory hotlist (<code>False</code>, by default) or edit current path (<code>True</code>).</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="SystemItemProperties"></a><SystemItemProperties></div></td>
<td class="hintcell">Linux/FreeBSD: the <code>True</code> value allows to use the file properties dialog window of the file manager, which is specified as the default program in the desktop environment settings (if it possible), otherwise, Double Commander will use its own <a href="Basic Help.md#cm_FileProperties">properties window</a>. <code>False</code> by default.</td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <SyncDirs>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="DateTimeFormat"></a><DateTimeFormat></div></td>
<td class="hintcell">This setting allows to specify the preferred date and time format in the <a href="Synchronize Directories.md">directory synchronization tool</a>. Date and time formatting symbols are described <a href="Configuration.md#dt_format">here</a>.<br>Default value is <code>yyyy.mm.dd hh:nn:ss</code>.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="SaveAsymmetric"></a>Attribute <i>Save</i><br><small>from <SyncDirs><Asymmetric></small></div></td>
<td class="hintcell">
              Synchronize directories: save or not asymmetric mode by default.<br>
              If we want to save state of mode then <code><Asymmetric Save="True"></code>
              or <code><Asymmetric Save="False"></code> otherwise (by default).
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="SaveFileMask"></a>Attribute <i>Save</i><br><small>from <SyncDirs><FileMask></small></div></td>
<td class="hintcell">
              Synchronize directories: by default, Double Commander saves the last used file mask as the mask for the next run of the synchronization tool (if it is not a search template),
              to disable this behavior, we can replace <code>True</code> with <code>False</code> (<code><FileMask Save="False"></code>) and specify the preferred file mask or "*" (i.e. all files) in the <code><FileMask></code> value.
            </td>
</tr>
<tr>
<td colspan="2" class="subsection"><div class="subsection">from <Viewer>:</div></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="AutoCopy"></a><AutoCopy></div></td>
<td class="hintcell">For the internal viewer, enables (<code>True</code>) or disables (<code>False</code>) automatic copying of the selected text to the clipboard. <code>True</code> by default.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ExtraLineSpanV"></a><ExtraLineSpan></div></td>
<td class="hintcell">
              For the internal viewer, this setting allows to add some extra pixels to the height allowed for each line. The value is interpreted directly in pixels.<br>
              Default value is 0.<br>
<i>Example:</i> <code><ExtraLineSpan>2</ExtraLineSpan></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="ImageExifRotate"></a><ImageExifRotate></div></td>
<td class="hintcell">
              Double Commander is able to recognize the <a href="https://en.wikipedia.org/wiki/Exif" target="_blank">EXIF</a> metadata format that might be encoded into a JPEG image file.<br>
              Inside that metadata, there is an <a href="https://www.impulseadventure.com/photo/exif-orientation.html" target="_blank">orientation flag</a> that may be used to display the picture into the same orientation as it was taken like if was in portrait, landscape, upside-down, mirror, etc.<br>
              The <code>ImageExifRotate</code> tag configures Double Commander to indicate if we want the viewer to display the image using that information or not.<br>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="innerdescvaluecell">True</td>
<td class="innerdescdesccell">Use the orientation flag embedded into the image file (default).</td>
</tr>
<tr>
<td class="innerdescvaluecell">False</td>
<td class="innerdescdesccell">Ignore the orientation flag.</td>
</tr>
</table>
<i>Example:</i> <code><ImageExifRotate>True</ImageExifRotate></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="JpegQuality"></a><JpegQuality></div></td>
<td class="hintcell">For the internal viewer, the quality value that Double Commander will use by default when saving to JPEG format (the commands <span class="italic">Save</span> and <span class="italic">Save As...</span>). 80 by default.</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="LeftMargin"></a><LeftMargin></div></td>
<td class="hintcell">
              For the internal viewer, this option allows to add space between the left border of the window and the text border. The value is interpreted directly in pixels.<br>
              Default value is 4.<br>
<i>Example:</i> <code><LeftMargin>4</LeftMargin></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="MaxCodeSize"></a><MaxCodeSize></div></td>
<td class="hintcell">
              For the internal viewer, limits the maximum file size for automatic choice of the code viewing mode (displaying text with syntax highlighting requires more resources than displaying plain text). The option value is ignored when we force the code viewing mode in the viewer window.<br>
              The size is specified in megabytes, the default value is 128.
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="MaxTextWidth"></a><MaxTextWidth></div></td>
<td class="hintcell">
              For the internal viewer, configure the maximum number of characters to be displayed on one text line prior to wrap it up to the next one.<br>
              The valid range goes from 80 to 16384 and default value is 1024.<br>
<i>Example:</i> <code><MaxTextWidth>1024</MaxTextWidth></code>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="SynEditMask"></a><SynEditMask></div></td>
<td class="hintcell">
              For the internal viewer, this option allows to manage the list of file extensions for code view mode (of course, within the available list).
              We can specify file masks (separated by semicolons ";" without spaces) that will automatically open in this mode instead of plain text, or the name of a search template to exclude. We can also disable automatic opening of files in this mode by setting an empty string.
              The default value is "*".
            </td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="TabSpaces"></a><TabSpaces></div></td>
<td class="hintcell">
              For the internal viewer, set the width of tab stops to use.<br>
              The valid range goes from 1 to 32 and default value is 8.<br>
<i>Example:</i> <code><TabSpaces>4</TabSpaces></code>
</td>
</tr>
</table>

## 4. Index

<table class="index">
<tr>
<td class="indexcell">
<p>
<a href="#Count">Attribute <i>Count</i> (<DirHistory>)</a><br>
<a href="#SaveAsymmetric">Attribute <i>Save</i> (<Asymmetric>)</a><br>
<a href="#SaveFileMask">Attribute <i>Save</i> (<FileMask>)</a><br><br>
<a href="#ActiveRight">ActiveRight</a><br>
<a href="#AutoCopy">AutoCopy</a><br>
<a href="#AutoExtractOpenMask">AutoExtractOpenMask</a><br>
<a href="#AutoSaveWidth">AutoSaveWidth</a><br>
<a href="#ConfirmQuit">ConfirmQuit</a><br>
<a href="#CopyAttributes">CopyAttributes</a><br>
<a href="#CopyTime">CopyTime</a><br>
<a href="#CopyXattributes">CopyXattributes</a><br>
<a href="#CustomIcons">CustomIcons</a><br>
<a href="#DateTimeFormat">DateTimeFormat</a>
</p>
</td>
<td class="indexcell">
<p>
<a href="#DecimalSeparator">DecimalSeparator</a><br>
<a href="#DefaultDropEffect">DefaultDropEffect</a><br>
<a href="#DiskAlpha">DiskAlpha</a><br>
<a href="#DoubleClickEditPath">DoubleClickEditPath</a><br>
<a href="#ExtraLineSpanF">ExtraLineSpan (<FilesViews>)</a><br>
<a href="#ExtraLineSpanV">ExtraLineSpan (<Viewer>)</a><br>
<a href="#FindWordAtCursor">FindWordAtCursor</a><br>
<a href="#FolderPrePostfix">FolderPrefix and FolderPostfix</a><br>
<a href="#gBorderFrameWidth">gBorderFrameWidth</a><br>
<a href="#ImageExifRotate">ImageExifRotate</a><br>
<a href="#JpegQuality">JpegQuality</a><br>
<a href="#LeftMargin">LeftMargin</a><br>
<a href="#LongInStatus">LongInStatus</a><br>
<a href="#LongNameAlert">LongNameAlert</a>
</p>
</td>
<td class="indexcell">
<p>
<a href="#MaxCodeSize">MaxCodeSize</a><br>
<a href="#MaxTextWidth">MaxTextWidth</a><br>
<a href="#Mode">Mode</a><br>
<a href="#NtfsHourTimeDelay">NtfsHourTimeDelay</a><br>
<a href="#Quality">Quality</a><br>
<a href="#RenameConfirmMouse">RenameConfirmMouse</a><br>
<a href="#ShowColonAfterDrive">ShowColonAfterDrive</a><br>
<a href="#Sounds">Sounds</a><br>
<a href="#SynEditMask">SynEditMask</a><br>
<a href="#SystemItemProperties">SystemItemProperties</a><br>
<a href="#TabSpaces">TabSpaces</a><br>
<a href="#TitleStyle">TitleStyle</a><br>
<a href="#ToolSize">ToolSize</a><br>
<a href="#UppercaseDriveLetter">UppercaseDriveLetter</a>
</p>
</td>
</tr>
</table>

---

[[Indice|← Index]]
