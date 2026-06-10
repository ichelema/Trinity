---
title: 2.16. Command line
source: commandline.html
tags: [doublecmd, documentation]
---

# Command Line

## Content

- 1. [[Command Line#1. Presentation|Presentation]]
- 2. [[Command Line#2. Possible parameters|Possible parameters]]
- 3. [[Command Line#3. Examples|Examples]]

## 1. Presentation

When launching Double Commander executable we may specify some command line parameters to customize our start up.

For example, we may specify the directories that will be displayed in the file panels.

There are some switches that may be used as well.

These switches are NOT case sensitive.

Here is a summary description of the syntax of what's possible in the command line:

`doublecmd.exe [-C] [-T] [-P L|R] [path1\subpath1] [path2\subpath2]`

An alternative form is also possible like this one:

`doublecmd.exe [-C] [-T] [-P L|R] [-L path1\subpath1] [-R path2\subpath2]`

Note: macOS command line has a some specificity, use the `open` command with the full application name ("Double Commander" with `-a`) and `--args` to pass parameters. For the second and subsequent instances, add `-n`.

## 2. Possible parameters

Here is the list of what may be present as parameters when launching Double Commander.

<table>
<tr class="rowcategorytitle"><th colspan="2">Command Line Parameters</th></tr>
<tr class="rowsubtitle"><th class="namecolumn">Parameter</th><th class="categorydesccolumn">Description</th></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft"><var>path1\sub1 [path2\sub2]</var><br><i><small class="firstcolumnaleft">(no switches, directly a path)</small></i></div></td>
<td class="hintcell">
              If one path passed then load it into the active panel.<br>
              If two paths are passed then load first path into left panel and second in the right panel.<br>
              Directory names containing spaces must be put in double quotes.<br>
              Always specify the full path name.
            </td>
</tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">-C <i>or</i> --client</div></td><td class="hintcell">If Double Commander is already running, activate it and pass the path(s) in the command line to that instance.</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">-L <i>directory</i></div></td><td class="hintcell">Set directory to show in the left panel.</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">-R <i>directory</i></div></td><td class="hintcell">Set directory to show in the right panel.</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">-P L|R</div></td><td class="hintcell">Sets the active panel when program starts:<ul><li><code>-P L</code> for left</li><li><code>-P R</code> right</li></ul></td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">-T</div></td><td class="hintcell">Opens the passed directory(ies) in new tab(s).</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">--config-dir=<i>path</i></div></td><td class="hintcell">Set custom directory path with DC configurations files.</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">--servername=x</div></td>
<td class="hintcell">
              Sets the name of the instance (server) DC, which can then be used to pass parameters.<br>
              If there is no already existing instance, then create it.<br>
              If there is already existing instance, and the current one is a client, then send params to the server (i.e. to the existing instance).<br>
              If there is already existing instance, and the current one is not a client, (i.e. <i>Allow only one copy of DC at a time</i> is false and no <code>--client</code>/<code>-c</code> options were given), then user-provided servername is altered: firstly, just add a trailing number "2".<br>
              If there is already some trailing number, then increase it by 1, until we found a servername that isn't busy yet, and then create instance with this servername.
            </td>
</tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">--no-splash</div></td><td class="hintcell">Disables the splash screen at startup DC.</td></tr>
<tr><td class="cmdcell"><div class="firstcolumnaleft">--debug-log=<i>file</i></div></td>
<td class="hintcell">
              Running Double Commander with sending the debug output to the specified file.<br>
              Also used module (Lazlogger) supports the environment variable <code>xxx_debuglog</code>, where <code>xxx</code> is the program file name without extension:
              in this case, it will be <code>doublecmd_debuglog</code>. If this environment variable exists, the file specified in its value will be used.<br>
              In Linux, it is preferable to use running in a terminal and redirecting the output to a file (both streams, stdout and stderr).
            </td>
</tr>
</table>

Note: If the full file name is specified instead of the directory, Double Commander will open the folder and move the cursor to this file.

## 3. Examples

Here is a few examples of wanted behaviors that could be done via command line parameters when launching Double Commander.

Open the directory `e:\Xilinx\ISE DS` in the left panel and the directory `c:\temp` in the right one:

```
doublecmd.exe "e:\Xilinx\ISE DS" c:\temp
```

Open directory `c:\Logs` in a new tab in the active panel of and already running instance of Double Commander:

```
doublecmd.exe -c -t c:\Logs
```

Start application with configuration files from directory `f:\Documents\DC\Job Settings` with the mention `JOB` in the title bar of application:

```
doublecmd.exe --config-dir="f:\Documents\DC\Job Settings" --servername="JOB"
```

![[cmdline.png|Example of command line|800]]

---

[[Indice|← Index]]
