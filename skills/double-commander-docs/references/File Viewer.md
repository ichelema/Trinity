---
title: 2.8. Built-in file viewer
source: viewer.html
tags: [doublecmd, documentation]
---

# 2.8. Built-in file viewer

## Content

- 1. [[File Viewer#1. Introduction|Introduction]]
- 2. [[File Viewer#2. Main menu|Main menu]]
  - 2.1. [[File Viewer#2.1. "File"|"File"]]
  - 2.2. [[File Viewer#2.2. "Edit"|"Edit"]]
  - 2.3. [[File Viewer#2.3. "View"|"View"]]
  - 2.4. [[File Viewer#2.4. "Plugins"|"Plugins"]]
  - 2.5. [[File Viewer#2.5. "Encoding"|"Encoding"]]
  - 2.6. [[File Viewer#2.6. "Image"|"Image"]]
  - 2.7. [[File Viewer#2.7. "About"|"About"]]
- 3. [[File Viewer#3. Toolbar|Toolbar]]
- 4. [[File Viewer#4. Status bar|Status bar]]
- 5. [[File Viewer#5. Preview|Preview]]
- 6. [[File Viewer#6. Copying/moving files|Copying/moving files]]
- 7. [[File Viewer#7. Quick view|Quick view]]
- 8. [[File Viewer#8. Additional settings|Additional settings]]

## 1. Introduction

The built-in viewer is designed to view files of any size in text, hexadecimal or binary format and image files.

![[viewer.png|Built-in file viewer]]

The selected text will be automatically copied to the clipboard, to disable we can use the [[doublecmd.xml Settings|<AutoCopy>]] parameter.

By default, the viewer (internal command `cm_View`) call is assigned to the `F3` key. If several files are selected, the first selected file will be opened and we can switch these files using the *Previous file* and *Next file* commands (otherwise, these commands will load files in the current directory). To open the file under the cursor anyway, we can use `Shift+F3`. We can change hotkeys in the [[Configuration#^ConfigHotKeys|Keys > Hot Keys]] settings section.

Supported image formats: BMP, CUR, GIF, ICNS, ICO, JPEG, PNG, PNM (PBM, PGM and PPM), PSD, SVG/SVGZ, TIFF, XPM. In addition, if the required libraries are available:

- HEIF/HEIC and AVIF: `libheif.dll` (Windows) or `libheif.so.1` (Linux and other Unix-like systems).
- SVG/SVGZ: `librsvg-2-2.dll`, `libcairo-2.dll` and `libgobject-2.0-0.dll` (Windows) or `librsvg-2.so.2`, `libcairo.so.2` and `libgobject-2.0.so.0` (Linux and other Unix-like systems). If these files are available, Double Commander will use the librsvg library instead of the built-in Image32 graphics library.
- WebP: `libwebp.so.N`, where "N" is 7, 6 or 5 (Linux and other Unix-like systems).
- Double Commander supports the TurboJPEG library, it is a JPEG codec that uses SIMD instructions to accelerate the decoding and encoding of images: `libturbojpeg.dll` (Windows), `libturbojpeg.so.0` (Linux and other Unix-like systems) or `libturbojpeg.dylib` (macOS).

Note: In Windows, libraries must be located near the Double Commander executable file, in the `plugins\dll` subdirectory near the executable file or in the Windows system directory.

Double Commander supports Windows Imaging Component (Windows Vista and newer): the Windows Imaging Component (WIC) provides an extensible framework for working with images. WIC includes several built-in codecs (BMP, DDS, GIF, ICO, JPEG, JPEG XR, PNG and TIFF), additionally available external codecs for free and proprietary RAW image formats, HEIF/HEIC, WebP. Double Commander will skip codecs for BMP, GIF, ICO, JPEG, PNG and TIFF, because these formats are already supported.

In Windows, Double Commander can use the built-in HEIC decoder (Windows 11 24H2 and newer).

The built-in viewer supports saving to the following image formats: BMP, ICO, JPEG (we can choose the quality from 1 to 100; 80 by default, see [[doublecmd.xml Settings|<JpegQuality>]]), PNG (Double Commander will use the same color depth as in the original image) and PNM (Double Commander will use binary formats, the color depth will be set automatically: 1, 8 or 24 bits per pixel).

Note: When modifying an image, we must save all changes with the *Save* or *Save As* commands: Double Commander does not check the status of the file (changed or not) when closing the viewer window or when switching to another file.

We can assign or change hotkeys for commands available in the viewer in the [[Configuration#^ConfigHotKeys|Keys > Hot Keys]] settings section (switch to the *Viewer* category). Hotkeys can be set separately for text mode and image viewing mode.

## 2. Main menu

The appearance and content of the main menu depends on the viewing mode: text, image or [[Configuration#^ConfigPlugins|WLX plugin]].

## 2.1. "File"

Items *Previous* and *Next* are used to load the previous or next file in the directory. If several files are selected, the commands will load these files. The sort order in the file panel is used.

Items *Save* and *Save As...* are available only when viewing images.

*Print...* – opens a system dialog for sending a file for printing. Printing is only available when viewed with plugins that support printing files.

*Print setup...* – opens a dialog for setting the print borders (left, right, top and bottom page margins).

*Reload* – Double Commander will forcibly reread the file without closing the viewer window. This is convenient if the file has been modified by an external program.

*Auto Reload* – only for text mode: if enabled, Double Commander will check the file size every 2 seconds and if it changes, reread the file and scroll its contents to the end. This is convenient for viewing constantly updated log files. This mode applies only to the current file and is disabled when switching to another file or when closing the viewer window. If enabled, Double Commander will show an asterisk "*" in the status bar before the file name.

*Exit* – Close the viewer window.

## 2.2. "Edit"

The menu contains commands for selecting and copying text, as well as commands for searching through the contents of the file being viewed: *Find*, *Find next* and *Find previous*.

Search options:

- *Case sensitive* – indicates that uppercase should be distinguished from lowercase, e.g. "Fallout" and "fallout" would be different.
- *Hexadecimal* – searches for hexadecimal characters (case insensitive, with or without spaces between characters, for example, "C0 C1 C2" or "c0c1c2").
- *Regular expressions* – if enabled we can use [[Regular Expressions|regular expressions]].
- *Backwards* – switches the search direction: search from the end of the file instead of searching from the beginning.

## 2.3. "View"

This menu is for switching the viewing mode and contains several additional options.

*Preview* – Show or hide the [[File Viewer#5. Preview]] panel.

The program automatically selects the appropriate file viewing mode, the following items allow to switch it forcibly:

- *Show as Text* – Show file contents (or console command output, see [[Configuration#^ConfigAssociations|File associations]]) as plain text. We can set the maximum number of characters to be displayed on one text line prior to wrap it up to the next one (1024 by default).
- *Show as Bin* – Show file contents as is. Non-printable characters will be displayed as dots, however, when copying text, control characters (line feed, carriage return, tabulation and so on) will be respected. A fixed line width of 80 characters is used.
- *Show as Hex* – The window will display three columns: offset from the beginning of the file (in bytes), 16 characters in hexadecimal representation and the same 16 characters in plain text. Non-printable characters will be displayed as dots. When selecting values in the second column, the corresponding symbols in the third column will be selected (and vice versa).
- *Show as Dec* – Like the previous, but bytes will be represented in decimal notation.
- *Show as Book* – A special viewing mode: text will be displayed in multiple columns (like a book spread or a newspaper). We can set the font and size, text and background colors, and the number of columns (1, 2 or 3).
- *Graphics* – switches to image viewing. See the list of supported image formats at the [[File Viewer#1. Introduction|beginning of the page]].
- *Plugins* – Viewing with WLX plugins. If the selected file can be opened by several installed plugins, then repeated calls of this command will switch them in a circle.
- *Office XML (text only)* – The viewer will show text from XML-based office documents: Microsoft Office (DOCX, XLSX) and OpenOffice/LibreOffice (ODT, ODS). Without text formatting, but preserving paragraphs.
- *Code* – The viewer will show the selected file in code view mode: with syntax highlighting and line numbers. The same highlighting rules and lists of extensions will be used as for the built-in text editor (see more details [[Configuration#^ConfigToolsEditorHL|here]]). In this mode, the viewer uses the [[Configuration#^ConfigToolsEditor|settings of the built-in editor]], also see the description of [[doublecmd.xml Settings|<SynEditMask>]].

Plugins have priority over other supported view modes.

*Wrap text* – enables or disables wrapping lines that do not fit in the window (by word boundaries).

*Show text cursor* – enables the display of a blinking text cursor.

## 2.4. "Plugins"

The menu contains a list of all added and enabled WLX plugins. The first part of the menu will contain plugins that are suitable for the current file (Double Commander checks the detection string), all others will be listed in the second part.

Without sorting, the same order is used in which the plugins were added in the corresponding settings section.

## 2.5. "Encoding"

When viewing files in text modes: menu with a list of available text encodings, auto-detection is enabled by default.

When using plugins, this menu includes only three items:

- *Auto-detect* – automatic encoding detection.
- *ANSI* – default system ANSI encoding (depends on the system locale).
- *OEM* – default system OEM (DOS) encoding (depends on the system locale).

## 2.6. "Image"

The *Image* menu will not be available when viewing GIF files.

*Stretch* – resizes the image so it fills the viewer window (the aspect ratio will be saved automatically).

*Stretch only large* – resizes the image only if it is larger than the current window size (the aspect ratio will be saved automatically).

*Center* – The image will be displayed in the center of the viewer window instead of the upper left corner.

*Show transparency* – enables the use of a checkerboard pattern as a background for transparent parts of the image.

The *Rotate* submenu includes several similar actions:

- The first three commands rotate the image by a specified number of degrees around its center: *+ 90* (90 degrees to the right), *+ 180* and *- 90* (90 degrees to the left).
- *Mirror Horizontally* – reverses the image horizontally, that is, from left to right.
- *Mirror Vertically* – reverses the image vertically, that is, from top to bottom.

*Zoom In* and *Zoom Out* – commands to change the image scale.

*Full Screen* – switches the window to full-screen mode (the contents of the window without the operating system's typical window-framing interface). This mode is available not only when viewing images, just use hotkeys (`Alt+Enter` by default).

The *Screenshot* submenu – creating a screenshot of the desktop, immediately or with a delay (3 or 5 seconds).

When using plugins, this menu includes only three items: *Stretch*, *Stretch only large* and *Center*.

## 2.7. "About"

Just a viewer name.

## 3. Toolbar

Several commands of the internal viewer and additional tools, collected in the toolbar. Only when viewing images.

![[viewertoolbar.png|Toolbar]]

*Reload current file* – Double Commander will forcibly reread the file without closing the viewer window. This is convenient if the file has been modified by an external program.

Buttons *Load Previous File* and *Load Next File* are used to load the previous or next file in the directory. The sort order in the file panel is used.

*Copy File* – see [[File Viewer#6. Copying/moving files|Copying/moving files]].

*Move File* – see [[File Viewer#6. Copying/moving files|Copying/moving files]].

*Delete File* – will delete the file being viewed with a confirmation request.

*Zoom In* and *Zoom Out* – commands to change the image scale.

*Rotate -90 degrees* – rotates the image by 90 degrees to the left around its center.

*Rotate +90 degrees* – rotates the image by 90 degrees to the right around its center.

*Mirror* – The *Mirror Horizontally* command: reverses the image horizontally, that is, from left to right.

The next group is for GIF animation only:

- *Pause/Play* – pauses animation playback.
- *Previous Frame* and *Next Frame* – switch animation frames back and forth.
- *Export Frame* – allows to save the current animation frame.

The next group of buttons is related to selection:

- *Highlight* – turns on the selection tool (rectangle).
- *Crop* – crop image by selection.
- *Red Eyes* – red-eye removal function.

The next group of buttons is related to drawing:

- *Paint* – enables drawing tools.
- *Undo* – cancels the last action.
- Menu for selecting a drawing tool: *Pen*, *Rect* and *Ellipse*.
- *Width* – Menu for selecting the line width (from 1 to 25 pixels).
- *Color* – allows to set the color of the line.

*Resize* – The image resizing tool allows to specify the width and height in pixels (the aspect ratio will be saved automatically).

*Full Screen* – switches the window to full-screen mode (the contents of the window without the operating system's typical window-framing interface) and back. This mode is available not only when viewing images, just use hotkeys (`Alt+Enter` by default).

When the window is expanded to full screen, an additional *Slide Show* button will become available: we can enable automatic loading the next image in the current directory and set the file display time (from 1 to 25 seconds).

## 4. Status bar

The appearance and content of the status bar depends on the viewing mode: text, image or WLX plugin.

At the beginning of the status bar, the number of the open file and the total number of files in the current directory are displayed.

Text: position in the file content (in bytes and percentages), file size and text encoding.

![[viewerstatus1.png|Status bar: text]]

Image: current resolution (in pixels and percentages), real file resolution and selection size (when using the selection tool).

![[viewerstatus2.png|Status bar: image]]

WLX plugin: plugin name and encoding.

![[viewerstatus3.png|Status bar: WLX plugin]]

At the ending of the status bar, the full name of the file being viewed is displayed.

## 5. Preview

Panel in the left part of the window, catalog files are displayed as thumbnails (with the file name below the thumbnail). It looks like the [[Basic Help#2.8. File Panels|thumbnail mode]] in the file panel.

![[viewerpreview.png|Preview]]

The sort order in the file panel is used. The file with which the viewer was launched will always be the first in the list.

The preview panel can be expanded to display a list of thumbnails in multiple columns.

Separate toolbar with several frequently used functions: *Reload current file*, *Load Previous File*, *Load Next File*, *Copy File*, *Delete File* and *Move File*, see description of similar buttons [[File Viewer#3. Toolbar|above]].

## 6. Copying/moving files

The viewer has the ability to copy or move the viewed file using hotkeys or buttons on the toolbar or on the preview panel (internal viewer commands `cm_CopyFile` and `cm_MoveFile`). We can specify up to 5 directories and switch between them:

![[viewercopymove.png|Copying/moving files]]

This is convenient if we need to put the viewed files into different directories or make an additional copy.

## 7. Quick view

Additional file viewing mode (`Ctrl+Q` by default): instead of a separate window, the contents of the file under the cursor will be shown in the opposite (inactive) file panel. As we navigate to next items, displayed content is updated, this allows to view the contents of files simply by moving the cursor in the file panel.

Quick view can be disabled by pressing `Ctrl+Q` again, also it will be disabled when switching any panel (active or inactive) to another tab.

"View" actions added in the [[Configuration#^ConfigAssociations|file association]] settings are ignored, except for applications that are launched with the `{!DC-VIEWER}` macro.

Not all viewer commands can work in this mode, for example, commands to load the previous or next file in the directory (`P` and `N` by default).

Right-click on the status bar brings up a menu that contains several submenus (depending on the current mode):

- "Plugins" mode: "View", "Plugins", "Encoding" and "Image";
- "Graphics" mode: "View", "Plugins" and "Image";
- other modes: "View", "Plugins" and "Encoding".

(See description above.)

Some interface elements may be hidden (for example, when viewing images in the "Graphics" mode, Double Commander will hide the toolbar). There is no general rule or recommendation for plugins, the decision is made by the plugin author.

## 8. Additional settings

See the description of the Double Commander settings sections: [[Configuration#^ConfigToolsViewer|Tools > Viewer]] and [[Configuration#^ConfigColor|Colors]] (the *Viewer* category). There are [[doublecmd.xml Settings|several parameters]] that can only be changed manually in the `doublecmd.xml` configuration file.

---

[[Indice|← Index]]
