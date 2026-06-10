---
title: 2.15. Lua Scripting
source: lua.html
tags: [doublecmd, documentation]
---

# 2.15. Lua Scripting

## Content

- 1. [[Lua Scripting#1. Introduction|Introduction]]
- 2. [[Lua Scripting#2. DLL required|DLL required]]
- 3. [[Lua Scripting#3. Double Commander functions libraries|Double Commander functions libraries]]
  - 3.1. [[Lua Scripting#3.1. DC library|DC library]]
    - 3.1.1. [[Lua Scripting#3.1.1. Example with the DC.ExecuteCommand|Example with the DC.ExecuteCommand]]
  - 3.2. [[Lua Scripting#3.2. System library|System library]]
    - 3.2.1. [[Lua Scripting#3.2.1. Details on SysUtils.FileGetAttr returned value|Details on SysUtils.FileGetAttr returned value]]
    - 3.2.2. [[Lua Scripting#3.2.2. Example with SysUtils.FileGetAttr|Example with SysUtils.FileGetAttr]]
    - 3.2.3. [[Lua Scripting#3.2.3. Example using FindFirst, FindNext and FindClose|Example using FindFirst, FindNext and FindClose]]
  - 3.3. [[Lua Scripting#3.3. Clipboard library|Clipboard library]]
    - 3.3.1. [[Lua Scripting#3.3.1. Example of usage clipboard library|Example of usage clipboard library]]
  - 3.4. [[Lua Scripting#3.4. Dialogs library|Dialogs library]]
    - 3.4.1. [[Lua Scripting#3.4.1. Buttons displayed in Dialogs.MessageBox|Buttons displayed in Dialogs.MessageBox]]
    - 3.4.2. [[Lua Scripting#3.4.2. Style of box of Dialogs.MessageBox|Style of box of Dialogs.MessageBox]]
    - 3.4.3. [[Lua Scripting#3.4.3. Default active button of Dialogs.MessageBox|Default active button of Dialogs.MessageBox]]
    - 3.4.4. [[Lua Scripting#3.4.4. Returned value of Dialogs.MessageBox|Returned value of Dialogs.MessageBox]]
    - 3.4.5. [[Lua Scripting#3.4.5. Example of usage of the Dialogs.MessageBox|Example of usage of the Dialogs.MessageBox]]
    - 3.4.6. [[Lua Scripting#3.4.6. Example of usage of the Dialogs.InputQuery|Example of usage of the Dialogs.InputQuery]]
  - 3.5. [[Lua Scripting#3.5. UTF-8 library|UTF-8 library]]
  - 3.6. [[Lua Scripting#3.6. Char library|Char library]]
  - 3.7. [[Lua Scripting#3.7. OS library|OS library]]
- 4. [[Lua Scripting#4. Index|Index]]

## 1. Introduction

Detailed information about the Lua scripting programming language can be found on the [Lua website](https://www.lua.org/).

Double Commander can execute Lua scripts via [[Internal Commands#cm_ExecuteScript]] command.
 Script parameters must be passed as is, without escaping (without quotes or "\"), for this we need to use the [[Variables in Parameters#7. Quotation in result or not|%"0]] variable: for example, `%"0%p0` for the file under cursor instead of `%p0` or `%"0%D` for the current directory instead of `%D`. Otherwise, if Double Commander automatically adds quotes, they will be passed as part of the parameter and you will have to take them into account.
 To get a list of all selected files we can use [[Variables in Parameters#9. List of files|variables]] (`%LU`, `%FU` or `%RU`) or internal commands ([[Internal Commands#cm_SaveSelectionToFile]], [[Internal Commands#cm_SaveFileDetailsToFile]], [[Internal Commands#cm_CopyFullNamesToClip]] or [[Internal Commands#cm_CopyFileDetailsToClip]]). We can use, for example, `%p`: in this case, Double Commander will pass the names of all selected files in one line, separating the names with a space.

It is also possible to write content plugins using Lua script, examples can be found in the program folder (`plugins/wdx/scripts`). The Wiki has a [page](https://github.com/doublecmd/doublecmd/wiki/Plugins-development) dedicated to writing plugins. Limitations: only the following data types are supported

- *ft_numeric_32* (1) – a 32-bit signed number;
- *ft_numeric_64* (2) – a 64-bit signed number;
- *ft_numeric_floating* (3) – a floating point number;
- *ft_boolean* (6) – boolean type: *true* or *false*;
- *ft_multiplechoice* (7) – a value allowing a limited number of choices;
- *ft_string* (8) – a text string;
- *ft_fulltext* (9) – a full text (multiple text strings), used only for searching with plugins;
- *ft_datetime* (10) – for date/time: a returned date will be converted to a formatted date and time string (value depends on your regional settings).
  The date must be in Windows format, but Lua and the functions that Double Commander provides for searching files use Unix time format. To convert we can use the formula:
  = UnixTime * 10000000 + 116444736000000000
  This is a large number, so you will need a 64-bit version of Double Commander or Lua 5.3+.

The list above contains the names from the header files, in Lua scripts we must use the numeric values which are specified in parentheses.

**About text encoding**

All additional functions described below accept string parameters in UTF-8 encoding and return strings in this encoding (except for the [[Lua Scripting#3.5. UTF-8 library|LazUtf8.ConvertEncoding]] function).

Some functions from the standard Lua libraries have been replaced with functions from Double Commander or Free Pascal/Lazarus (or new ones have been written), this provides UTF-8 support.

When writing plugins, we should also use UTF-8 for text data (*ft_multiplechoice*, *ft_string* and *ft_fulltext*).

When saving scripts, use UTF-8 encoding without BOM.

**Notes**

Automation with Lua has great possibilities, but there may be nuances that in some cases need to be kept in mind. Let's try to collect them in this subsection.

1. If [[Configuration#^ConfigRefresh|auto refresh]] and the [[Configuration#^ConfigViewEx|Load file list in separate thread]] option are enabled, the refresh function will work asynchronously. At the same time, scripts are executed in the main thread of Double Commander and therefore, in some cases, all this may affect the operation of your script. For example, sometimes sequential execution of [[Internal Commands#2.10. Navigation|commands for navigation]] may not work (for example, large directories, slow disk), in this case try to disable *Load file list in separate thread* or look for an alternative solution.

If your script creates new files in the current panel or renames existing files, but then does not complete and performs some additional actions (for example, selecting files or moving the cursor), then in some cases these actions will not have an effect: not all files may be in the panel yet and you will need to first call the [[Internal Commands#cm_Refresh]] command. Under the described conditions, `cm_Refresh` will also be executed asynchronously and Double Commander may not have time to completely refresh the list of files after your changes.

Auto-refreshing and loading the list of files in a separate thread are convenient functions for a file manager, so the stable working method was experimentally found to temporarily return control to the program and allow the file list to be completely refreshed:

```lua
DC.ExecuteCommand("cm_Refresh")
i = 10
while i > 0 do
  SysUtils.Sleep(10)
  DC.ExecuteCommand("")
  i = i - 1
end
```

2. Lua function `io.open` uses the standard C function `fopen`: in text mode, this function can convert the type of line endings (CRLF, LF or CR) when reading and writing and it can lead to unexpected results. If you come across files with different types of line endings or if you are writing a cross-platform script, this must be taken into account or it may be more practical to give preference to the binary mode.

3. For the [[Basic Help#^cm_FileProperties|file properties]] dialog in Linux and other Unix-like operating systems, the `ContentGetValue` function is called with the `CONTENT_DELAYIFSLOW` flag (the fourth parameter, the value is 1), this avoids the delay in opening the window: if data retrieval is slow, we can exclude this data by simply adding a flag value check and returning `nil` for such fields or plugin.

4. If the plugin should return an empty string, it will be faster to pass `nil` instead of `""`.

## 2. DLL required

In order to interpret Lua script file, we need to have a Lua DLL file, Double Commander supports versions 5.1 - 5.4.

We can use DLL file from [LuaJIT project](https://luajit.org/). LuaJIT combines a high-speed interpreter, written in assembler, with a state-of-the-art JIT compiler. Also we get FFI library, which allows calling external C functions and using C data structures from pure Lua code.

DC distributives for Windows have Lua DLL by default (in DC 0.9.7 and newer from LuaJIT project), in other cases we may find and install it through our packages manager or compile it. If we're using a 64-bits version of DC, the DLL must be the 64-bits version as well.

By default DC looks for a file with name `lua5.1.dll` (Windows), `liblua5.1.so.0` (Unix or GNU/Linux) or `liblua5.1.dylib` (macOS) in its directory and in the system directory. We can change the file name (and path) in the [[Configuration#^luapathtolibrary|Lua library file to use]] parameter.

## 3. Double Commander functions libraries

Double Commander offer a few libraries of functions for our Lua scripts.

Here is the list of them.

| List of libraries |  |  |
| --- | --- | --- |
| Library name | Script name | Quick description |
| [[Lua Scripting#3.1. DC library\|Double Commander library]] | DC | Double Commander specific functions |
| [[Lua Scripting#3.2. System library\|System library]] | SysUtils | Various system functions |
| [[Lua Scripting#3.3. Clipboard library\|Clipboard library]] | Clipbrd | Provides external clipboard functionality |
| [[Lua Scripting#3.4. Dialogs library\|Dialogs library]] | Dialogs | Interacts with user |
| [[Lua Scripting#3.5. UTF-8 library\|UTF-8 library]] | LazUtf8 | UTF-8 string functions |
| [[Lua Scripting#3.6. Char library\|Char library]] | Char | Getting information about characters |
| [[Lua Scripting#3.7. OS library\|OS library]] | os | Functions related with the operating system |

## 3.1. DC library

This library contains Double Commander specific functions.

It provides all its functions inside the table `DC`.

<table>
<tr class="rowcategorytitle"><th colspan="2">DC library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_logwrite"></a>DC.LogWrite</div></td>
<td class="hintcell">
<p class="definition">DC.LogWrite(sMessage, iMsgType, bForce, bLogFile)</p>
<p>Write a message to the log window:</p>
<ul>
<li><var>sMessage</var> : The message text.</li>
<li><var>iMsgType</var> : The message type: 0 - information, 1 - success, 2 - error.</li>
<li><var>bForce</var> : A boolean, when true, will show the log window if invisible.</li>
<li><var>bLogFile</var> : A boolean, when true, will write the message also in the log file.</li>
</ul>
<p>The internal function of Double Commander for writing to the protocol works asynchronously (see notes in the <a href="#preface">introduction</a>), so messages from <code>DC.LogWrite</code> will not be written to the protocol immediately, but after the script is completed. If it is necessary to write the text immediately, we can try to add the call <code>DC.ExecuteCommand("")</code> after <code>DC.LogWrite</code>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_currentpanel"></a>DC.CurrentPanel</div></td>
<td class="hintcell">
<p class="definition">iPanel = DC.CurrentPanel()</p>
<p>Get active panel: returns 0 if left panel is active or 1 if right.</p>
<p class="definition">DC.CurrentPanel(iPanel)</p>
<p>Set active panel: left panel if <var>iPanel</var> equal 0 or right if 1.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_executecommand"></a>DC.ExecuteCommand</div></td>
<td class="hintcell">
<p class="definition">DC.ExecuteCommand(sCommand, Param1, Param2,...,ParamX)</p>
<p>This allows the script to invoke <a href="Internal Commands.md">internal commands</a> of Double Commander.</p>
<p>The <var>sCommand</var> is holding the actual internal command name.</p>
<p>We may provide as many <var>Param...</var> as command may support.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_gotofile"></a>DC.GoToFile</div></td>
<td class="hintcell">
<p class="definition">DC.GoToFile(sFileName, bActive)</p>
<p>Opens the directory where <var>sFileName</var> is located and places the cursor on <var>sFileName</var>. To open a directory, use <a href="Internal Commands.md#cm_ChangeDir">cm_ChangeDir</a> or try to add the directory separator and ".." (without quotes) to <var>sFileName</var>.</p>
<p><var>bActive</var> is an optional parameter: function can work in the active file panel (<code>true</code>) or inactive one (<code>false</code>). <code>true</code> by default.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_getpluginfield"></a>DC.GetPluginField</div></td>
<td class="hintcell">
<p class="definition">Result = DC.GetPluginField(sFileName, sPlugin, iField, iUnit)</p>
<p>Allows to get data using the installed content plugin (WDX):</p>
<ul>
<li><var>sFileName</var> : The full (absolute) filename.</li>
<li><var>sPlugin</var> : The plugin name, as it is saved in the corresponding <a href="Configuration.md#ConfigPlugins">settings section</a>.</li>
<li><var>iField</var> : The plugin field index (counting from 0).</li>
<li><var>iUnit</var> : The unit index (counting from 0); specify 0 if it does not exist.</li>
<li><var>Result</var> : The return value: signed number (including time in Unix format), floating point number, boolean value, text string or <code>nil</code>.</li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dc_expandvar"></a>DC.ExpandVar</div></td>
<td class="hintcell">
<p class="definition">sResult = DC.ExpandVar(String)</p>
<p>Returns a string in which all <a href="Variables in Parameters.md">variables</a> are replaced with their values (excluding environment variables, use <a href="#sysutils_expandenv">SysUtils.ExpandEnv</a> for them).</p>
</td>
</tr>
</table>

In addition to internal commands, in scripts we can use the special command `cm_ExecuteToolBarItem`, this command allows to call toolbar buttons by their identifier (in the program, this function provides the use of hotkeys for toolbar buttons). The command is used similarly to ordinary internal commands (see examples below) and has the following parameters:

| Parameter | Value | Description |
| --- | --- | --- |
| ToolBarID | TfrmOptionsToolbar | the button of the main toolbar |
| TfrmOptionsToolbarMiddle | the button of the middle toolbar |  |
| *(absent)* | the button of the main toolbar |  |
| ToolItemID | *identifier* | the unique identifier of the button |

The unique identifier is stored in the `ID` tag and we have several ways to get it: we can find the button in the `doublecmd.xml` file, in the toolbar backup file, or simply copy the button to the clipboard and paste its code into a text editor.

Note: Identifiers are generated automatically and do not have to match the identifiers of similar buttons in another copy of the program, but if necessary, we can manually set our own value.

## 3.1.1. Example with the DC.ExecuteCommand

In this example, we wrote a simple script that will do the following:

1. focus to right panel
2. close all opened tabs
3. switch to a specific folder
4. focus the left panel
5. close all opened tabs
6. switch to a specific folder
7. open a new tab
8. switch to a specific folder

```lua
-- 1. Focus on right panel.
DC.ExecuteCommand("cm_FocusSwap", "side=right")

-- 2. Close all tabs.
DC.ExecuteCommand("cm_CloseAllTabs")

-- 3. Switch to a specific directory.
DC.ExecuteCommand("cm_ChangeDir", "E:\\FakeKey\\Documents\\Music")

-- 4. Focus on left panel.
DC.ExecuteCommand("cm_FocusSwap", "side=left")

-- 5. Close all tabs.
DC.ExecuteCommand("cm_CloseAllTabs")

-- 6. Switch to a specific directory.
DC.ExecuteCommand("cm_ChangeDir", "C:\\Users\\Public\\Music")

-- 7. Open a new tab.
DC.ExecuteCommand("cm_NewTab")

-- 8. Switch to a specific directory.
DC.ExecuteCommand("cm_ChangeDir", "E:\\VirtualMachines\\ShareFolder")
```

Using the internal command [[Internal Commands#cm_ExecuteScript]], we may configure a tool bar button that will execute our script.

Assuming this script file is `E:\scripts\lua\music.lua`, we could have the button configured this way:

![[luaimg1.png|Invoking a Lua script from toolbar]]

Also, we may use the internal Double Commander Editor for editing our scripts. If filename has `.lua` file extension, it will be recognized by internal editor and it will provide us syntax highlighting specific for this Lua language:

![[luaimg2.png|Lua syntax highlighting with internal editor]]

## 3.2. System library

This library contains various system functions.

It provides all its functions inside the table `SysUtils`.

<table>
<tr class="rowcategorytitle"><th colspan="2">System library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_sleep"></a>SysUtils.Sleep</div></td>
<td class="hintcell">
<p class="definition">SysUtils.Sleep(iMilliseconds)</p>
<p>Suspends the execution of the script for the specified number of <var>iMilliseconds</var>.<br>After the specified period has expired, script execution resumes.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_gettickcount"></a>SysUtils.GetTickCount</div></td>
<td class="hintcell">
<p class="definition">SysUtils.GetTickCount()</p>
<p>Returns an increasing clock tick count. It is useful for time measurements, but no assumptions should be made as to the interval between the ticks.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_fileexists"></a>SysUtils.FileExists</div></td>
<td class="hintcell">
<p class="definition">bExists = SysUtils.FileExists(sFileName)</p>
<p>Check whether a particular file exists in the filesystem.</p>
<p>Returns in <var>bExists</var> the value <code>true</code> if file with name <var>sFileName</var> exists on the disk, or <code>false</code> otherwise.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_directoryexists"></a>SysUtils.DirectoryExists</div></td>
<td class="hintcell">
<p class="definition">bExists = SysUtils.DirectoryExists(sDirectory)</p>
<p>Checks whether <var>sDirectory</var> exists in the filesystem and is actually a directory.</p>
<p>If this is the case, the function returns in <var>bExists</var> the value <code>true</code> otherwise <code>false</code> is returned.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_filegetattr"></a>SysUtils.FileGetAttr</div></td>
<td class="hintcell">
<p class="definition">iAttr = SysUtils.FileGetAttr(sFileName)</p>
<p>Returns in <var>iAttr</var> the attribute settings of file <var>sFileName</var>.</p>
<p>See the detail explanations of the returned value <a href="#detailattr">here</a>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_findfirst"></a>SysUtils.FindFirst</div></td>
<td class="hintcell">
<p class="definition">Handle, FindData = SysUtils.FindFirst(sPath)</p>
<p>Looks for files that match the <var>sPath</var>, generally with wildcards.</p>
<p>If no file is found, <var>Handle</var> will be <code>nil</code>.</p>
<p>When at least one item is found, the returned <var>Handle</var> may be used in subsequent <code>SysUtils.FindNext</code> to find other occurrences of the same pattern.</p>
<p>The <var>FindData</var> table contains information about the file or directory found.</p>
<p>The field of the <var>FindData</var> table are:</p>
<ul>
<li><var>Name</var> : The file name (without path).</li>
<li><var>Attr</var> : The file attributes of the file (see details <a href="#detailattr">here</a>).</li>
<li><var>Size</var> : The size of the file in bytes.</li>
<li><var>Time</var> : The time stamp of the file (seconds since Jan 01 1970)</li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_findnext"></a>SysUtils.FindNext</div></td>
<td class="hintcell">
<p class="definition">Result, FindData = SysUtils.FindNext(Handle)</p>
<p>Finds the next occurrence of a search sequence initiated by <code>FindFirst</code> by re-using the <var>Handle</var> returned previously.</p>
<p>Returned <var>Result</var> will be non-nil if a file or directory is found and will be <code>nil</code> otherwise.</p>
<p>The same notes mentioned for <code>SysUtils.FindFirst</code> applied here.</p>
<p><b><span class="uline">Remark:</span> The last <code>SysUtils.FindNext</code> call must always be followed by a <code>SysUtils.FindClose</code> call with the same <var>Handle</var>. Failure to do so will result in memory leaks.</b></p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_findclose"></a>SysUtils.FindClose</div></td>
<td class="hintcell">
<p class="definition">SysUtils.FindClose(Handle)</p>
<p>Ends a series of <code>SysUtils.FindFirst</code>/<code>SysUtils.FindNext</code> calls.</p>
<p>Frees any memory used by these calls.</p>
<p>It is <em>absolutely</em> necessary to do this call, or memory losses may occur.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_createdirectory"></a>SysUtils.CreateDirectory</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.CreateDirectory(sDirectory)</p>
<p>Create a chain of directories, <var>sDirectory</var> is the full path to directory.</p>
<p>Returns <code>true</code> if <var>sDirectory</var> already exist or was created successfully. If it failed to create any of the parts, <code>false</code> is returned.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_removedirectory"></a>SysUtils.RemoveDirectory</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.RemoveDirectory(sDirectory)</p>
<p>Will delete the directory with the name <var>sDirectory</var>. Returns <code>true</code> if successful, <code>false</code> otherwise.</p>
<p>Unlike <a href="#os_remove">os.remove</a>, this function does not return a description in case of an error, but it can delete non-empty directories.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_createhardlink"></a>SysUtils.CreateHardLink</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.CreateHardLink(sFileName, sLinkName)</p>
<p>Create the hard link <var>sLinkName</var> to file <var>sFileName</var>.</p>
<p>Returns <code>true</code> if successful, <code>false</code> otherwise.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_createsymboliclink"></a>SysUtils.CreateSymbolicLink</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.CreateSymbolicLink(sFileName, sLinkName)</p>
<p>Create the symbolic link <var>sLinkName</var> to file or directory <var>sFileName</var>.</p>
<p>Returns <code>true</code> if successful, <code>false</code> otherwise.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_readsymboliclink"></a>SysUtils.ReadSymbolicLink</div></td>
<td class="hintcell">
<p class="definition">sTarget = SysUtils.ReadSymbolicLink(sLinkName, bRecursive)</p>
<p>Read destination of the symbolic link <var>sLinkName</var>.</p>
<p>If <var>bRecursive</var> is <code>true</code> and the link points to a link then it's resolved recursively until a valid file name that is not a link is found.</p>
<p>Returns the path where the symbolic link <var>sLinkName</var> is pointing to or an empty string when the link is invalid or the file it points to does not exist and <var>bRecursive</var> is <code>true</code>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_extractfilename"></a>SysUtils.ExtractFileName</div></td>
<td class="hintcell">
<p class="definition">sName = SysUtils.ExtractFileName(sFileName)</p>
<p>Extract the filename part from a full path filename.</p>
<p>The filename consists of all characters after the last directory separator character ("/" or "\") or drive letter.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_extractfileext"></a>SysUtils.ExtractFileExt</div></td>
<td class="hintcell">
<p class="definition">sExt = SysUtils.ExtractFileExt(sFileName)</p>
<p>Return the extension from a filename (all characters after the last "." (dot), including the "." character).</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_extractfilepath"></a>SysUtils.ExtractFilePath</div></td>
<td class="hintcell">
<p class="definition">sPath = SysUtils.ExtractFilePath(sFileName)</p>
<p>Extract the path from a filename (including drive letter).</p>
<p>The path consists of all characters before the last directory separator character ("/" or "\"), including the directory separator itself.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_extractfiledir"></a>SysUtils.ExtractFileDir</div></td>
<td class="hintcell">
<p class="definition">sDir = SysUtils.ExtractFileDir(sFileName)</p>
<p>Extract only the directory part of <var>sFileName</var>, including a drive letter.</p>
<p>The directory name has NO ending directory separator, in difference with <code>SysUtils.ExtractFilePath</code>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_extractfiledrive"></a>SysUtils.ExtractFileDrive</div></td>
<td class="hintcell">
<p class="definition">sDrive = SysUtils.ExtractFileDrive(sFileName)</p>
<p>Extract the drive part from a filename.</p>
<p>Note that some operating systems do not support drive letters.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_getabsolutepath"></a>SysUtils.GetAbsolutePath</div></td>
<td class="hintcell">
<p class="definition">sName = SysUtils.GetAbsolutePath(sFileName, sBaseDirectory)</p>
<p>Returns the absolute (full) path to the file:</p>
<ul>
<li><var>sFileName</var> : The filename with a relative path.</li>
<li><var>sBaseDirectory</var> : The directory that was used as the base directory for <var>sFileName</var>.</li>
</ul>
<p>If the absolute path could not be obtained, the function will return the <var>sFileName</var> value.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_getrelativepath"></a>SysUtils.GetRelativePath</div></td>
<td class="hintcell">
<p class="definition">sName = SysUtils.GetRelativePath(sFileName, sBaseDirectory)</p>
<p>Returns the filename relative to the specified directory:</p>
<ul>
<li><var>sFileName</var> : The full (absolute) filename.</li>
<li><var>sBaseDirectory</var> : The directory that will be used as the base directory <var>sFileName</var>.</li>
</ul>
<p>If <var>sFileName</var> and <var>sBaseDirectory</var> contain the same value, the function will return an empty string (""). If it was not possible to get the file name with a relative path, the function will return the <var>sFileName</var> value.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_matchesmask"></a>SysUtils.MatchesMask</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.MatchesMask(sFileName, sMask, iMaskOptions)</p>
<p>Returns <code>true</code> if <var>sFileName</var> matches the passed mask <var>sMask</var>.</p>
<p><var>iMaskOptions</var> (optional parameter, 0 by default) is set as the sum of the following values:</p>
<table class="innercmddesc">
<tr class="rowinnerdesc">
<th class="innerdescheader">Value</th>
<th class="innerdescheader">Description</th>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">1</div></td>
<td class="hintcell">case sensitive</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">2</div></td>
<td class="hintcell">ignore accents and ligatures</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">4</div></td>
<td class="hintcell">Windows style filter: "*.*" also match files without extension, etc.</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">8</div></td>
<td class="hintcell">enable pinyin support (file <tt>pinyin.tbl</tt> will be used)</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_matchesmasklist"></a>SysUtils.MatchesMaskList</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.MatchesMaskList(sFileName, sMaskList, sSeparator, iMaskOptions)</p>
<p>Returns <code>true</code> if <var>sFileName</var> matches at least one of passed masks <var>sMaskList</var> separated by <var>sSeparator</var> (";" by default).</p>
<p><var>sSeparator</var> and <var>iMaskOptions</var> (see above) are optional parameters.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_execute"></a>SysUtils.Execute</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.Execute(sCommand)</p>
<p>Will execute <var>sCommand</var> as it would be typed on the command-line and return <code>true</code> if successful and <code>false</code> otherwise (the function does not wait for the executed command to complete).</p>
<p>Note: In Windows, the <a href="#os_execute">os.execute</a> function opens a terminal window every time, but the <code>SysUtils.Execute</code> function does not have this drawback.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_expandenv"></a>SysUtils.ExpandEnv</div></td>
<td class="hintcell">
<p class="definition">sResult = SysUtils.ExpandEnv(String, bSpecial)</p>
<p>Returns a string in which all environment variables are replaced with their values for the current user.</p>
<p><var>bSpecial</var> is an optional parameter: if <code>true</code>, pseudo environment variables will also be expanded (see details <a href="Variables in Parameters.md#envvariables">here</a>). <code>false</code> by default.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_gettempname"></a>SysUtils.GetTempName</div></td>
<td class="hintcell">
<p class="definition">sTempFileName = SysUtils.GetTempName()</p>
<p>Will return a filename to use as a temporary filename (in the system directory for the temporary files), similar to the <a href="#libraryos">os.tmpname</a> function, but the file will be created in the <tt>_dc~~~</tt> subdirectory that is automatically deleted when Double Commander is closed.<br>If the function could not create a unique name, it will return an empty string.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_getfileproperty"></a>SysUtils.GetFileProperty</div></td>
<td class="hintcell">
<p class="definition">Result = SysUtils.GetFileProperty(sFileName, iValue)</p>
<p>Returns the file property corresponding to <var>iValue</var>:</p>
<table class="innercmddesc">
<tr class="rowinnerdesc"><th class="innerdescheader">Value</th><th class="innerdescheader">Description</th>
</tr><tr><td class="innerdescvaluecell">0</td><td class="innerdescdesccell">File size in bytes</td></tr>
<tr><td class="innerdescvaluecell">1</td><td class="innerdescdesccell">String of attributes as in the file panel (for a detailed description of the string value, see <a href="Configuration.md#ConfigColorFiles">here</a>)</td></tr>
<tr><td class="innerdescvaluecell">2</td><td class="innerdescdesccell">Group of the file owner</td></tr>
<tr><td class="innerdescvaluecell">3</td><td class="innerdescdesccell">Owner of the file</td></tr>
<tr><td class="innerdescvaluecell">4</td><td class="innerdescdesccell">Modification date</td></tr>
<tr><td class="innerdescvaluecell">5</td><td class="innerdescdesccell">Creation date</td></tr>
<tr><td class="innerdescvaluecell">6</td><td class="innerdescdesccell">Last access date</td></tr>
<tr><td class="innerdescvaluecell">7</td><td class="innerdescdesccell">Status change date</td></tr>
<tr><td class="innerdescvaluecell">8</td><td class="innerdescdesccell">File type (as in Windows Explorer or MIME-type)</td></tr>
<tr><td class="innerdescvaluecell">9</td><td class="innerdescdesccell">Description (comment) from <tt>descript.ion</tt> (see details <a href="Basic Help.md#cm_EditComment">here</a>)</td></tr>
</table>
<p>Returns a number (file size, timestamps) or a string (in other cases). In case of failure, function returns <code>nil</code>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_filesettime"></a>SysUtils.FileSetTime</div></td>
<td class="hintcell">
<p class="definition">bResult = SysUtils.FileSetTime(sFileName, iModification, iCreation, iLastAccess)</p>
<p>Allows to set timestamps (Unix time format) for <var>sFileName</var>: modification date, creation date and last access date. Specify zero for those timestamps that should be ignored.</p>
<p>Returns <code>true</code> if successful, <code>false</code> otherwise.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="sysutils_pathdelim"></a>SysUtils.PathDelim</div></td>
<td class="hintcell">
<p class="definition">SysUtils.PathDelim</p>
<p>The character used by the current operating system to separate directory names in the full file name.</p>
<p>In Unix/Linux system the directory separator will be "/" and in Windows it will be "\".</p>
</td>
</tr>
</table>

## 3.2.1. Details on SysUtils.FileGetAttr returned value

`FileGetAttr` returns the attribute settings of file *sFileName*.

The attribute is a *OR*-ed combination of the following constants:

| Constants uses in SysUtils.FileGetAttr returned value |  |
| --- | --- |
| Value | Signification |
| 0x00000001  faReadOnly | The file is read-only. |
| 0x00000002  faHidden | The file is hidden.<br>In Unix/Linux, this means that the filename starts with a dot. |
| 0x00000004  faSysFile | The file is a system file.<br>In Unix/Linux, this means that the file is a character or block device, a named pipe (FIFO). |
| 0x00000008  faVolumeId | Volume Label.<br>Only for DOS/Windows on a plain FAT (not VFAT or FAT32) filesystem. |
| 0x00000010  faDirectory | File is a directory. |
| 0x00000020  faArchive | File is archived.<br>Not possible in Unix/Linux. |
| 0x00000400  faSymLink | File is a symbolic link. |
| **Note: In case of an error, -1 is returned.** |  |

See an example in the [[Lua Scripting#3.2.2. Example with SysUtils.FileGetAttr|next section]].

## 3.2.2. Example with SysUtils.FileGetAttr

This following script is an example of usage of the `SysUtils.FileGetAttr`.

When the parameter is detected to be a directory, it will open a new tab in the active panel and switch to it.

```lua
local params = {...}
local iAttr

if #params == 1 then -- We got at least one parameter?
  iAttr = SysUtils.FileGetAttr(params[1])
  if iAttr > 0 then -- We got a valid attribute?
    if math.floor(iAttr / 0x00000010) % 2 ~= 0 then
      -- bit 4 is set? So it's a directory.
      DC.ExecuteCommand("cm_NewTab")
      DC.ExecuteCommand("cm_ChangeDir", params[1])
    end
  end
end
```

In the above example, the *params[1]* is the 1st parameter passed to the script.

When using the internal command [[Internal Commands#cm_ExecuteScript]], it will will be the first parameter passed after the script filename.

So in our example, we may program a sample toolbar button like the following:

![[luaimg3.png|Parameter with cm_ExecuteScript]]

In this example, the parameter `%"0%p` will be passed to the script. This will represent, unquoted, the filename of the item currently selected in the active panel at the moment we press the toolbar button.

## 3.2.3. Example using FindFirst, FindNext and FindClose

In the following script example, we'll scan the content of the directory we received in parameter and store resulting data into a text file with the filename passed as a second parameter.

This will give us a good idea of the usage of `FindFirst`, `FindNext` and `FindClose`.

```lua
local params = {...}

if #params == 2 then -- We got our 2 parameters?
  local Result = nil
  local hOutputFile = nil

  hOutputFile = io.output(params[2])

  local Handle, FindData = SysUtils.FindFirst(params[1] .. "\\*")
  if Handle ~= nil then
    repeat
      io.write(FindData.Name .. "\r")
      io.write(FindData.Size .. "\r")
      io.write("---------------\r")

      Result, FindData = SysUtils.FindNext(Handle)
    until Result == nil

    SysUtils.FindClose(Handle)
    io.close(hOutputFile)
  end
end
```

In the above example, we need to pass two parameters to our script:

1. *params[1]* - which is the directory we want the content
2. *params[2]* - which is the outputfilename to store the result

So it's easy to configure a toolbar button using the internal command [[Internal Commands#cm_ExecuteScript]] and pass the parameter to accomplish all this.

![[luaimg4.png|Parameter with cm_ExecuteScript]]

In this example, the parameter `%"0%Ds` will be passed to the script as the first parameter. This will represent, unquoted, the directory displayed by the active panel.

## 3.3. Clipboard library

Double Commander may provide external clipboard functionality to our Lua scripts.

Following table gives us the related functions:

<table>
<tr class="rowcategorytitle"><th colspan="2">Clipboard library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="clipbrd_clear"></a>Clipbrd.Clear</div></td>
<td class="hintcell">
<p class="definition">Clipbrd.Clear()</p>
<p>Clear the content of the clipboard.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="clipbrd_getastext"></a>Clipbrd.GetAsText</div></td>
<td class="hintcell">
<p class="definition">sVar = Clipbrd.GetAsText()</p>
<p>Get the current text content of the clipboard to assigned it to <var>sVar</var>. If the clipboard does not contain text, the function returns an empty string.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="clipbrd_setastext"></a>Clipbrd.SetAsText</div></td>
<td class="hintcell">
<p class="definition">Clipbrd.SetAsText(sVar)</p>
<p>Store in the clipboard the text content of <var>sVar</var>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="clipbrd_setashtml"></a>Clipbrd.SetAsHtml</div></td>
<td class="hintcell">
<p class="definition">Clipbrd.SetAsHtml(sHtml)</p>
<p>Adds html-formatted text <var>sHtml</var> to the clipboard (<code>CF_HTML</code> clipboard format).</p>
<p>This contents will be inserted in applications which support this clipboard format, like MS Word, LO Writer, etc.</p>
<p>It's correct to store data with both <code>Clipbrd.SetAsText</code> and <code>Clipbrd.SetAsHtml</code>. When we'll paste, the application will use the best one that it supports.</p>
<p>For example we may have this:</p>
<ul>
<li><code>Clipbrd.SetAsText("Welcome to Double Commander!")</code></li>
<li><code>Clipbrd.SetAsHtml("Welcome to <b>Double Commander</b>!")</code></li>
</ul>
<p>If we switch to Notepad attempting to paste something, it will paste in plain text the message we copied with <code>Clipbrd.SetAsText</code>. But if we switch to Microsoft Word and paste something, it will paste the second one, the one with <b>Double Commander</b> in bold since the Microsoft Word recognize and support that clipboard content type.</p>
</td>
</tr>
</table>

## 3.3.1. Example of usage clipboard library

The following example is using three functions related with the clipboard: `Clear`, `GetAsText` and `SetAsText`.

It's a relative long script but it's good to put together a few functions we've seen above.

It assumes our active panel is currently into a directory with many source text files.

It also assumes we currently have in clipboard a single word and that it will receive as a single parameter the current active folder.

The script will scan the file in that current level of directory and will read the content of them one by one to detect text line that contains the word that was in clipboard.

Then, the filenames of the files that contain at least one line with that word will be place into the clipboard.

Then, the script will use the internal command [[Internal Commands#cm_LoadSelectionFromClip]] and the files that have the words will then be selected.

Also, at the end, we put back in our clipboard the original word that needed to be searched.

```lua
local params = {...}
local Result = nil
local iAttr
local bFound = false
local sCompleteFilename = ""
local hInputFile = nil
local sLine = ""
local iPosS
local iPosE
local sFileToSelect = ""
local sSearchString = ""

if #params == 1 then -- We got our parameter?
  sSearchString = Clipbrd.GetAsText() -- Get the expression to search.
  Clipbrd.Clear() -- Making sure we have nothing in clipboard.
  DC.ExecuteCommand("cm_MarkUnmarkAll") -- Make sure nothing is selected.

  -- Let's scan one by one all the files of our directory.
  local Handle, FindData = SysUtils.FindFirst(params[1] .. "\\*")
  if Handle ~= nil then
    repeat
      sCompleteFilename = params[1] .. "\\" .. FindData.Name
      iAttr = SysUtils.FileGetAttr(sCompleteFilename)
      if iAttr > 0 then -- We got a valid attribute?
        -- We need file, not directory!
        if math.floor(iAttr / 0x00000010) % 2 == 0 then

          -- Let's now read the file line by line until the the end OR a found.
          hInputFile = io.open(sCompleteFilename, "r")
          bFound = false

          while bFound == false do
            sLine = hInputFile:read()
            if sLine == nil then break end
            iPosS, iPosE = string.find(sLine, sSearchString)
            if iPosS ~= nil then bFound = true end
          end

          if bFound == true then
            sFileToSelect = sFileToSelect .. FindData.Name .. "\n"
          end

          io.close(hInputFile)
        end
      end
      Result, FindData = SysUtils.FindNext(Handle)
    until Result == nil

    SysUtils.FindClose(Handle)
  end

  -- If we've found something, select it!
  if sFileToSelect ~= "" then
    Clipbrd.SetAsText(sFileToSelect)
    DC.ExecuteCommand("cm_LoadSelectionFromClip")
  end

  Clipbrd.SetAsText(sSearchString) -- Restoring what we had in clipboard.
end
```

## 3.4. Dialogs library

This library allows our scripts to interact with user to display message, prompt for answers, etc.

Following table gives us the related functions:

<table>
<tr class="rowcategorytitle"><th colspan="2">Dialogs library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dialogs_messagebox"></a>Dialogs.MessageBox</div></td>
<td class="hintcell">
<p class="definition">iButton = Dialogs.MessageBox(sMessage, sTitle, iFlags)</p>
<p>Will display a message box prompting a user to click a button which will be returned by the function:</p>
<ul>
<li><var>sMessage</var> : The message inside the box.</li>
<li><var>sTitle</var> : The text displayed as the title of the box.</li>
<li><var>iFlags</var> : OR'ed value of constants to determine the buttons that will be displayed, the style of window and default button selected for the answer. See the following table the <a href="#dlgbuts">buttons displayed</a>, <a href="#dlgstyle">style of window</a> or <a href="#dlgdefbut">default button</a>.</li>
<li><var>iButton</var> : Returned value indicating the button user pressed (see <a href="#msgreturn">this table</a>).</li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dialogs_inputquery"></a>Dialogs.InputQuery</div></td>
<td class="hintcell">
<p class="definition">bResult, sAnswer = Dialogs.InputQuery(sTitle, sMessage, bMask, sDefault)</p>
<p>Will display a requester box where user may enter a string value:</p>
<ul>
<li><var>sTitle</var> : The text displayed as the title of the box.</li>
<li><var>sMessage</var> : The message inside the box.</li>
<li><var>bMask</var> : A boolean, when true, will display "stars" to hide characters.</li>
<li><var>sDefault</var> : The default suggested text that user may type over if necessary.</li>
<li><var>bResult</var> : Returned boolean indicating if user effectively enter something or not.</li>
<li><var>sAnswer</var> : Returned string when user entered something and then clicked ok.</li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="dialogs_inputlistbox"></a>Dialogs.InputListBox</div></td>
<td class="hintcell">
<p class="definition">sItem, iItem = Dialogs.InputListBox(sTitle, sMessage, aItems, sDefault)</p>
<p>Displays a dialog box to allow the user to choose from a list of items:</p>
<ul>
<li><var>sTitle</var> : The text displayed as the title of the dialog.</li>
<li><var>sMessage</var> : The message inside the dialog.</li>
<li><var>aItems</var> : A Lua table, each element of the table must be a string.</li>
<li><var>sDefault</var> : The default selected item in the list.</li>
<li><var>sItem</var> : Returned the selected item as a string or <code>nil</code> if the dialog is dismissed.</li>
<li><var>iItem</var> : Index of the selected item (counting from one, as is customary in Lua tables).</li>
</ul>
</td>
</tr>
</table>

## 3.4.1. Buttons displayed in Dialogs.MessageBox

The buttons displayed in the box displayed by `Dialogs.MessageBox` function are controlled by a OR'ed value with one of the following:

<table>
<tr class="rowcategorytitle"><th colspan="2">Constant of ButFlags regarding the buttons displayed of Dialogs.MessageBox</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Constant value</th><th class="categorydesccolumn">Buttons displayed, from left to right</th></tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0000<br><small class="firstcolumnaleft">MB_OK</small></div></td>
<td class="hintcell">
<img src="images/luaimg11.png" alt="Button OK">
</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0001<br><small class="firstcolumnaleft">MB_OKCANCEL</small></div></td>
<td class="hintcell">
<img src="images/luaimg11.png" alt="Button OK">
<img src="images/luaimg12.png" alt="Button CANCEL">
</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0002<br><small class="firstcolumnaleft">MB_ABORTRETRYIGNORE</small></div></td>
<td class="hintcell">
<img src="images/luaimg15.png" alt="Button ABORT">
<img src="images/luaimg14.png" alt="Button RETRY">
<img src="images/luaimg13.png" alt="Button IGNORE">
</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0003<br><small class="firstcolumnaleft">MB_YESNOCANCEL</small></div></td>
<td class="hintcell">
<img src="images/luaimg16.png" alt="Button YES">
<img src="images/luaimg17.png" alt="Button NO">
<img src="images/luaimg12.png" alt="Button CANCEL">
</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0004<br><small class="firstcolumnaleft">MB_YESNO</small></div></td>
<td class="hintcell">
<img src="images/luaimg16.png" alt="Button YES">
<img src="images/luaimg17.png" alt="Button NO">
</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0005<br><small class="firstcolumnaleft">MB_RETRYCANCEL</small></div></td>
<td class="hintcell">
<img src="images/luaimg14.png" alt="Button RETRY">
<img src="images/luaimg12.png" alt="Button CANCEL">
</td>
</tr>
</table>

## 3.4.2. Style of box of Dialogs.MessageBox

The style of the box displayed by `Dialogs.MessageBox` function are controlled by a OR'ed value with one of the following:

<table>
<tr class="rowcategorytitle"><th colspan="2">Constant of ButFlags regarding the icon and style of Dialogs.MessageBox</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Constant value</th><th class="categorydesccolumn">Style of window</th></tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0040<br><small class="firstcolumnaleft">MB_ICONINFORMATION</small></div></td>
<td class="hintcell"><img src="images/luaimg8.png" alt="Icon INFORMATION"> Informative window</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0030<br><small class="firstcolumnaleft">MB_ICONWARNING</small></div></td>
<td class="hintcell"><img src="images/luaimg9.png" alt="Icon WARNING"> Warning window</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0020<br><small class="firstcolumnaleft">MB_ICONQUESTION</small></div></td>
<td class="hintcell"><img src="images/luaimg7.png" alt="Icon QUESTION"> Confirmation window</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0010<br><small class="firstcolumnaleft">MB_ICONERROR</small></div></td>
<td class="hintcell"><img src="images/luaimg10.png" alt="Icon ERROR"> Error window</td>
</tr>
</table>

## 3.4.3. Default active button of Dialogs.MessageBox

The default active button of the box displayed by `Dialogs.MessageBox` function are controlled by a OR'ed value with one of the following:

| Constant of ButFlags regarding the default button of Dialogs.MessageBox |  |
| --- | --- |
| Constant value | Default button |
| 0x0000  MB_DEFBUTTON1 | Default will be the first one on left |
| 0x0100  MB_DEFBUTTON2 | Default will be the second one from left |
| 0x0200  MB_DEFBUTTON3 | Default will be the third one from left |

## 3.4.4. Returned value of Dialogs.MessageBox

The number returned by the `Dialogs.MessageBox` function represent the button user has pressed according to the following:

<table>
<tr class="rowcategorytitle"><th colspan="2">ButPressed value returned based on button pressed of Dialogs.MessageBox</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Constant value</th><th class="categorydesccolumn">Button pressed</th></tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0000<br><small class="firstcolumnaleft">mrNone</small></div></td>
<td class="hintcell">No button pressed</td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0001<br><small class="firstcolumnaleft">mrOK</small></div></td>
<td class="hintcell"><img src="images/luaimg11.png" alt="Result OK"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0002<br><small class="firstcolumnaleft">mrCancel</small></div></td>
<td class="hintcell"><img src="images/luaimg12.png" alt="Result CANCEL"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0003<br><small class="firstcolumnaleft">mrAbort</small></div></td>
<td class="hintcell"><img src="images/luaimg15.png" alt="Result ABORT"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0004<br><small class="firstcolumnaleft">mrRetry</small></div></td>
<td class="hintcell"><img src="images/luaimg14.png" alt="Result RETRY"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0005<br><small class="firstcolumnaleft">mrIgnore</small></div></td>
<td class="hintcell"><img src="images/luaimg13.png" alt="Result IGNORE"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0006<br><small class="firstcolumnaleft">mrYes</small></div></td>
<td class="hintcell"><img src="images/luaimg16.png" alt="Result YES"></td>
</tr>
<tr>
<td class="varcell"><div class="firstcolumnaleft">0x0007<br><small class="firstcolumnaleft">mrNo</small></div></td>
<td class="hintcell"><img src="images/luaimg17.png" alt="Result NO"></td>
</tr>
</table>

Note: If we press the "x" in top right or press `Esc` to close the window, then the value of the button "Cancel" is will returned.

## 3.4.5. Example of usage of the Dialogs.MessageBox

Here is a little script using `Dialogs.MessageBox` and the resulting window that will be displayed:

```lua
-- Buttons displayed
MB_OK = 0x0000
MB_OKCANCEL = 0x0001
MB_ABORTRETRYIGNORE = 0x0002
MB_YESNOCANCEL = 0x0003
MB_YESNO = 0x0004
MB_RETRYCANCEL = 0x0005

-- Box style
MB_ICONINFORMATION = 0x0040
MB_ICONWARNING = 0x0030
MB_ICONQUESTION = 0x0020
MB_ICONERROR = 0x0010

-- Default button
MB_DEFBUTTON1 = 0x0000
MB_DEFBUTTON2 = 0x0100
MB_DEFBUTTON3 = 0x0200

-- Returned button pressed
mrNone = 0x0000
mrOK = 0x0001
mrCancel = 0x0002
mrAbort = 0x0003
mrRetry = 0x0004
mrIgnore = 0x0005
mrYes = 0x0006
mrNo = 0x0007

iFlags = MB_YESNO + MB_ICONQUESTION + MB_DEFBUTTON2
iButton = Dialogs.MessageBox("Do you want to quit?", "Question", iFlags)

if iButton == mrYes then
  DC.ExecuteCommand("cm_Exit")
end
```

![[luaimg6.png|Example of usage of the Dialogs.MessageBox]]

## 3.4.6. Example of usage of the Dialogs.InputQuery

Here is a little script using `Dialogs.InputQuery` and the resulting window that will be displayed:

```lua
bResult, sAnswer = Dialogs.InputQuery("Identification", "Enter your name:", false, "John")

if bResult == true then
  Dialogs.MessageBox("Hello " .. sAnswer .. "!", "Welcome!", 0x0040)
end
```

![[luaimg5.png|Example of usage of the Dialogs.InputQuery]]

## 3.5. UTF-8 library

This library provides basic support for UTF-8 encoding.

It provides all its functions inside the table `LazUtf8`.

<table>
<tr class="rowcategorytitle"><th colspan="2">UTF-8 library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_pos"></a>LazUtf8.Pos</div></td>
<td class="hintcell">
<p class="definition">iResult = LazUtf8.Pos(SearchText, SourceText, Offset)</p>
<p>Search for substring in a string, starting at a certain position. The search is case sensitive.</p>
<p>Returns the position of the first occurrence of the substring <var>SearchText</var> in the string <var>SourceText</var>, starting the search at position <var>Offset</var> (default 1).</p>
<p>If <var>SearchText</var> does not occur in <var>SourceText</var> after the given <var>Offset</var>, zero is returned.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_next"></a>LazUtf8.Next</div></td>
<td class="hintcell">
<p class="definition">LazUtf8.Next(String)</p>
<p>An iterator function that, each time it is called, returns the next character in the <var>String</var> and the position of the beginning of this character (in bytes).</p>
<p>Example:</p>
<pre>
<span class="luacmt">-- Print pairs of values in the form "position : character"</span>
<span class="luakyw">for</span> iPos<span class="luasbl">,</span> sChar <span class="luakyw">in</span> <span class="mark">LazUtf8.Next</span><span class="luasbl">(</span>String<span class="luasbl">)</span> <span class="luakyw">do</span>
  DC.LogWrite<span class="luasbl">(</span>iPos <span class="luasbl">..</span> <span class="luastr">" : "</span> <span class="luasbl">..</span> sChar<span class="luasbl">)</span>
<span class="luakyw">end</span></pre>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_copy"></a>LazUtf8.Copy</div></td>
<td class="hintcell">
<p class="definition">sResult = LazUtf8.Copy(String, iIndex, iCount)</p>
<p>Copy part of a string.</p>
<p>Copy returns a string which is a copy if the <var>iCount</var> characters in <var>String</var>, starting at position <var>iIndex</var>.</p>
<p>If <var>iCount</var> is larger than the length of the string <var>String</var>, the result is truncated. If <var>iIndex</var> is larger than the length of the string <var>String</var>, then an empty string is returned.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_length"></a>LazUtf8.Length</div></td>
<td class="hintcell">
<p class="definition">iResult = LazUtf8.Length(String)</p>
<p>Returns the number of UTF-8 characters in the string.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_uppercase"></a>LazUtf8.UpperCase</div></td>
<td class="hintcell">
<p class="definition">sResult = LazUtf8.UpperCase(String)</p>
<p>Receives a string and returns a copy of this string with all lowercase letters changed to uppercase.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_lowercase"></a>LazUtf8.LowerCase</div></td>
<td class="hintcell">
<p class="definition">sResult = LazUtf8.LowerCase(String)</p>
<p>Receives a string and returns a copy of this string with all uppercase letters changed to lowercase.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_convertencoding"></a>LazUtf8.ConvertEncoding</div></td>
<td class="hintcell">
<p class="definition">sResult = LazUtf8.ConvertEncoding(String, FromEnc, ToEnc)</p>
<p>Convert <var>String</var> encoding from <var>FromEnc</var> to <var>ToEnc</var>.</p>
<p>List of supported encoding values:</p>
<ul>
<li>Default system encoding (depends on the system locale): "default".</li>
<li>Default ANSI (Windows) encoding (depends on the system locale): "ansi".</li>
<li>Default OEM (DOS) encoding (depends on the system locale): "oem".</li>
<li>Unicode: "utf8", "utf8bom", "ucs2le", "ucs2be".</li>
<li>ANSI (Windows): "cp1250", "cp1251", "cp1252", "cp1253", "cp1254", "cp1255", "cp1256", "cp1257", "cp1258".</li>
<li>OEM (DOS): "cp437", "cp850", "cp852", "cp865", "cp866", "cp874", "cp932", "cp936", "cp949", "cp950".</li>
<li>ISO 8859: "iso88591", "iso88592", "iso88593", "iso88594", "iso88595", "iso88597", "iso88599", "iso885910", "iso885913", "iso885914", "iso885915", "iso885916".</li>
<li>Other: "macintosh", "koi8r", "koi8u",  "koi8ru".</li>
</ul>
              The meaning of special encodings (examples).
              <br><br>
              In Windows (English or Russian):
              <ul>
<li>"default" - cp1252 or cp1251</li>
<li>"ansi" - cp1252 or cp1251</li>
<li>"oem" - cp850 or cp866</li>
</ul>
              In Linux (English or Russian):
              <ul>
<li>"default" - utf8</li>
<li>"ansi" - cp1252 or cp1251</li>
<li>"oem" - cp850 or cp866</li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="lazutf8_detectencoding"></a>LazUtf8.DetectEncoding</div></td>
<td class="hintcell">
<p class="definition">sEnc = LazUtf8.DetectEncoding(String)</p>
<p>Returns the value of encoding of the transmitted text.<br>The list of supported encodings is similar to those used in the <code>LazUtf8.ConvertEncoding</code> function.</p>
</td>
</tr>
</table>

## 3.6. Char library

This library contains functions for checking whether a character belongs to a particular Unicode category, as well as getting the category of a character.

List of available functions in this library:

<table>
<tr class="rowcategorytitle"><th colspan="2">Char library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_getunicodecategory"></a>Char.GetUnicodeCategory</div></td>
<td class="hintcell">
<p class="definition">iResult = Char.GetUnicodeCategory(Character)</p>
<p>Returns the Unicode category of a character <code>Character</code>, one of the following values:</p>
<table class="innercmddesc">
<tr class="rowinnerdesc"><th class="innerdescheader">Value</th><th class="innerdescheader">Description</th>
</tr><tr><td colspan="2">  Letter:</td></tr>
<tr><td class="innerdescvaluecell">0</td><td class="innerdescdesccell">Uppercase Letter (Lu)</td></tr>
<tr><td class="innerdescvaluecell">1</td><td class="innerdescdesccell">Lowercase Letter (Ll)</td></tr>
<tr><td class="innerdescvaluecell">2</td><td class="innerdescdesccell">Titlecase Letter (Lt)</td></tr>
<tr><td class="innerdescvaluecell">3</td><td class="innerdescdesccell">Modifier Letter (Lm)</td></tr>
<tr><td class="innerdescvaluecell">4</td><td class="innerdescdesccell">Other Letter (Lo)</td></tr>
<tr><td colspan="2">  Mark:</td></tr>
<tr><td class="innerdescvaluecell">5</td><td class="innerdescdesccell">Non-Spacing Mark (Mn)</td></tr>
<tr><td class="innerdescvaluecell">6</td><td class="innerdescdesccell">Spacing Combining Mark (Mc)</td></tr>
<tr><td class="innerdescvaluecell">7</td><td class="innerdescdesccell">Enclosing Mark (Me)</td></tr>
<tr><td colspan="2">  Number:</td></tr>
<tr><td class="innerdescvaluecell">8</td><td class="innerdescdesccell">Decimal Digit Number (Nd)</td></tr>
<tr><td class="innerdescvaluecell">9</td><td class="innerdescdesccell">Letter Number (Nl)</td></tr>
<tr><td class="innerdescvaluecell">10</td><td class="innerdescdesccell">Other Number (No)</td></tr>
<tr><td colspan="2">  Punctuation:</td></tr>
<tr><td class="innerdescvaluecell">11</td><td class="innerdescdesccell">Connector Punctuation (Pc)</td></tr>
<tr><td class="innerdescvaluecell">12</td><td class="innerdescdesccell">Dash Punctuation (Pd)</td></tr>
<tr><td class="innerdescvaluecell">13</td><td class="innerdescdesccell">Open Punctuation (Ps)</td></tr>
<tr><td class="innerdescvaluecell">14</td><td class="innerdescdesccell">Close Punctuation (Pe)</td></tr>
<tr><td class="innerdescvaluecell">15</td><td class="innerdescdesccell">Initial Punctuation (Pi)</td></tr>
<tr><td class="innerdescvaluecell">16</td><td class="innerdescdesccell">Final Punctuation (Pf)</td></tr>
<tr><td class="innerdescvaluecell">17</td><td class="innerdescdesccell">Other Punctuation (Po)</td></tr>
<tr><td colspan="2">  Symbol:</td></tr>
<tr><td class="innerdescvaluecell">18</td><td class="innerdescdesccell">Math Symbol (Sm)</td></tr>
<tr><td class="innerdescvaluecell">19</td><td class="innerdescdesccell">Currency Symbol (Sc)</td></tr>
<tr><td class="innerdescvaluecell">20</td><td class="innerdescdesccell">Modifier Symbol (Sk)</td></tr>
<tr><td class="innerdescvaluecell">21</td><td class="innerdescdesccell">Other Symbol (So)</td></tr>
<tr><td colspan="2">  Separator:</td></tr>
<tr><td class="innerdescvaluecell">22</td><td class="innerdescdesccell">Space Separator (Zs)</td></tr>
<tr><td class="innerdescvaluecell">23</td><td class="innerdescdesccell">Line Separator (Zl)</td></tr>
<tr><td class="innerdescvaluecell">24</td><td class="innerdescdesccell">Paragraph Separator (Zp)</td></tr>
<tr><td colspan="2">  Other:</td></tr>
<tr><td class="innerdescvaluecell">25</td><td class="innerdescdesccell">Control (Cc)</td></tr>
<tr><td class="innerdescvaluecell">26</td><td class="innerdescdesccell">Format (Cf)</td></tr>
<tr><td class="innerdescvaluecell">27</td><td class="innerdescdesccell">Surrogate (Cs)</td></tr>
<tr><td class="innerdescvaluecell">28</td><td class="innerdescdesccell">Private Use (Co)</td></tr>
<tr><td class="innerdescvaluecell">29</td><td class="innerdescdesccell">Unassigned (Cn)</td></tr>
</table>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_isdigit"></a>Char.IsDigit</div></td>
<td class="hintcell">
<p class="definition">bResult = Char.IsDigit(Character)</p>
<p>Returns <code>true</code> if the <var>Character</var> character is in the <i>Nd</i> category.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_isletter"></a>Char.IsLetter</div></td>
<td class="hintcell">
<p class="definition">bResult = Char.IsLetter(Character)</p>
<p>Returns <code>true</code> if the <var>Character</var> character is in the category <i>Lu</i>, <i>Ll</i>, <i>Lt</i>, <i>Lm</i> or <i>Lo</i>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_isletterordigit"></a>Char.IsLetterOrDigit</div></td>
<td class="hintcell">
<p class="definition">bResult = Char.IsLetterOrDigit(Character)</p>
<p>Returns <code>true</code> if the <var>Character</var> character is in the category <i>Lu</i>, <i>Ll</i>, <i>Lt</i>, <i>Lm</i> <i>Lo</i>, <i>Nd</i> или <i>Nl</i>.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_islower"></a>Char.IsLower</div></td>
<td class="hintcell">
<p class="definition">bResult = Char.IsLower(Character)</p>
<p>Returns <code>true</code> if the <var>Character</var> character is in the <i>Ll</i> category.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="char_isupper"></a>Char.IsUpper</div></td>
<td class="hintcell">
<p class="definition">bResult = Char.IsUpper(Character)</p>
<p>Returns <code>true</code> if the <var>Character</var> character is in the <i>Lu</i> category.</p>
</td>
</tr>
</table>

Also, these functions support working with two parameters: instead of a single character, we can specify a string and the position of the character in this string.

## 3.7. OS library

This library contains functions related with the operating system where Double Commander is running.

Here is the list of available functions in this library:

<table>
<tr class="rowcategorytitle"><th colspan="2">OS library</th></tr>
<tr class="rowsubtitle"><th class="categorynamecolumn">Function name</th><th class="categorydesccolumn">Description</th></tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_execute"></a>os.execute</div></td>
<td class="hintcell">
<p class="definition">iResultCode = os.execute(sCommand)</p>
<p>Will execute <var>sCommand</var> as it would be typed on the command-line and return the result code of the operation.</p>
<p>The <var>sCommand</var> could either be:</p>
<ul>
<li>A terminal command like <code>os.execute("dir > all.txt")</code></li>
<li>An executable like <code>os.execute("C:\\Windows\\System32\\calc.exe")</code></li>
<li>An executable with parameters:<br><code>os.execute("C:\\Utils\\fsum.exe -md5 test.bin > md5.txt")</code></li>
</ul>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_tmpname"></a>os.tmpname</div></td>
<td class="hintcell">
<p class="definition">sTempFileName = os.tmpname()</p>
<p>Will return a filename to use as a temporary filename (in the system directory for the temporary files).<br>If the function could not create a unique name, it will return an empty string.</p>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_remove"></a>os.remove</div></td>
<td class="hintcell">
<p class="definition">bResult, sError, iError = os.remove(sFileName)</p>
<p>Will delete the file or the directory with the name <var>sFileName</var>.</p>
<p>If it works, function returns <code>true</code>.</p>
<p>If it fails, function returns three things:</p>
<ol>
<li><code>nil</code> to indicate it failed</li>
<li><var>sError</var> for the error message description</li>
<li><var>iError</var> for the error code number</li>
</ol>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_rename"></a>os.rename</div></td>
<td class="hintcell">
<p class="definition">bResult, sError, iError = os.rename(sOldName, sNewName)</p>
<p>Will rename the file <var>sOldName</var> with the new name <var>sNewName</var>.</p>
<p><b><span class="uline">Note:</span> If a file named <var>sNewName</var> already exists, it will be replaced!</b></p>
<p>If it works, function returns <code>true</code>.</p>
<p>If it fails, function returns three things:</p>
<ol>
<li><code>nil</code> to indicate it failed</li>
<li><var>sError</var> for the error message description</li>
<li><var>iError</var> for the error code number</li>
</ol>
</td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_getenv"></a>os.getenv</div></td>
<td class="hintcell">
<p class="definition">Value = os.getenv(VariableName)</p>
<p>Will return the <var>Value</var> of the variable <var>VariableName</var> passed in parameter.<br>If no variable of that name exists, it will return <code>nil</code>.</p></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_setenv"></a>os.setenv</div></td>
<td class="hintcell">
<p class="definition">os.setenv(VariableName, Value)</p>
<p>Add or change the <var>VariableName</var> environment variable. In case of an error, the function returns -1.</p></td>
</tr>
<tr>
<td class="cmdcell"><div class="firstcolumnaleft"><a id="os_unsetenv"></a>os.unsetenv</div></td>
<td class="hintcell">
<p class="definition">os.unsetenv(VariableName)</p>
<p>Remove the <var>VariableName</var> environment variable. In case of an error, the function returns -1.</p></td>
</tr>
</table>

## 4. Index

<table class="index">
<tr>
<td class="indexcell">
<p><span class="bold"><a href="#libdc">DC library</a></span></p>
<p>
<a href="#dc_currentpanel">DC.CurrentPanel</a><br>
<a href="#dc_executecommand">DC.ExecuteCommand</a><br>
<a href="#dc_expandvar">DC.ExpandVar</a><br>
<a href="#dc_getpluginfield">DC.GetPluginField</a><br>
<a href="#dc_gotofile">DC.GoToFile</a><br>
<a href="#dc_logwrite">DC.LogWrite</a>
</p>
<br>
<p><span class="bold"><a href="#librarysystem">System library</a></span></p>
<p>
<a href="#sysutils_createdirectory">SysUtils.CreateDirectory</a><br>
<a href="#sysutils_createhardlink">SysUtils.CreateHardLink</a><br>
<a href="#sysutils_createsymboliclink">SysUtils.CreateSymbolicLink</a><br>
<a href="#sysutils_directoryexists">SysUtils.DirectoryExists</a><br>
<a href="#sysutils_execute">SysUtils.Execute</a><br>
<a href="#sysutils_expandenv">SysUtils.ExpandEnv</a><br>
<a href="#sysutils_extractfiledir">SysUtils.ExtractFileDir</a><br>
<a href="#sysutils_extractfiledrive">SysUtils.ExtractFileDrive</a><br>
<a href="#sysutils_extractfileext">SysUtils.ExtractFileExt</a><br>
<a href="#sysutils_extractfilename">SysUtils.ExtractFileName</a><br>
<a href="#sysutils_extractfilepath">SysUtils.ExtractFilePath</a><br>
<a href="#sysutils_fileexists">SysUtils.FileExists</a><br>
<a href="#sysutils_filegetattr">SysUtils.FileGetAttr</a><br>
<a href="#sysutils_filesettime">SysUtils.FileSetTime</a><br>
<a href="#sysutils_findclose">SysUtils.FindClose</a><br>
<a href="#sysutils_findfirst">SysUtils.FindFirst</a><br>
<a href="#sysutils_findnext">SysUtils.FindNext</a><br>
<a href="#sysutils_getabsolutepath">SysUtils.GetAbsolutePath</a><br>
<a href="#sysutils_getfileproperty">SysUtils.GetFileProperty</a><br>
<a href="#sysutils_getrelativepath">SysUtils.GetRelativePath</a><br>
<a href="#sysutils_gettempname">SysUtils.GetTempName</a><br>
<a href="#sysutils_gettickcount">SysUtils.GetTickCount</a><br>
<a href="#sysutils_matchesmask">SysUtils.MatchesMask</a><br>
<a href="#sysutils_matchesmasklist">SysUtils.MatchesMaskList</a><br>
<a href="#sysutils_pathdelim">SysUtils.PathDelim</a><br>
<a href="#sysutils_readsymboliclink">SysUtils.ReadSymbolicLink</a><br>
<a href="#sysutils_removedirectory">SysUtils.RemoveDirectory</a><br>
<a href="#sysutils_sleep">SysUtils.Sleep</a>
</p>
<br>
</td>
<td class="indexcell">
<p><span class="bold"><a href="#libraryclip">Clipboard library</a></span></p>
<p>
<a href="#clipbrd_clear">Clipbrd.Clear</a><br>
<a href="#clipbrd_getastext">Clipbrd.GetAsText</a><br>
<a href="#clipbrd_setashtml">Clipbrd.SetAsHtml</a><br>
<a href="#clipbrd_setastext">Clipbrd.SetAsText</a>
</p>
<br>
<p><span class="bold"><a href="#librarydialogs">Dialogs library</a></span></p>
<p>
<a href="#dialogs_inputlistbox">Dialogs.InputListBox</a><br>
<a href="#dialogs_inputquery">Dialogs.InputQuery</a><br>
<a href="#dialogs_messagebox">Dialogs.MessageBox</a>
</p>
<br>
<p><span class="bold"><a href="#libraryutf8">UTF-8 library</a></span></p>
<p>
<a href="#lazutf8_convertencoding">LazUtf8.ConvertEncoding</a><br>
<a href="#lazutf8_copy">LazUtf8.Copy</a><br>
<a href="#lazutf8_detectencoding">LazUtf8.DetectEncoding</a><br>
<a href="#lazutf8_length">LazUtf8.Length</a><br>
<a href="#lazutf8_lowercase">LazUtf8.LowerCase</a><br>
<a href="#lazutf8_next">LazUtf8.Next</a><br>
<a href="#lazutf8_pos">LazUtf8.Pos</a><br>
<a href="#lazutf8_uppercase">LazUtf8.UpperCase</a>
</p>
<br>
<p><span class="bold"><a href="#librarychar">Char library</a></span></p>
<p>
<a href="#char_getunicodecategory">Char.GetUnicodeCategory</a><br>
<a href="#char_isdigit">Char.IsDigit</a><br>
<a href="#char_isletter">Char.IsLetter</a><br>
<a href="#char_isletterordigit">Char.IsLetterOrDigit</a><br>
<a href="#char_islower">Char.IsLower</a><br>
<a href="#char_isupper">Char.IsUpper</a>
</p>
<br>
</td>
<td class="indexcell">
<p><span class="bold"><a href="#libraryos">OS library</a></span></p>
<p>
<a href="#os_execute">os.execute</a><br>
<a href="#os_getenv">os.getenv</a><br>
<a href="#os_remove">os.remove</a><br>
<a href="#os_rename">os.rename</a><br>
<a href="#os_setenv">os.setenv</a><br>
<a href="#os_tmpname">os.tmpname</a><br>
<a href="#os_unsetenv">os.unsetenv</a>
</p>
</td>
</tr>
</table>

---

[[Indice|← Index]]
