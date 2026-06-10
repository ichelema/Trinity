---
title: 2.18. Pre-installed plugins
source: plugins.html
tags: [doublecmd, documentation]
---

# 2.18. Pre-installed plugins

## Content

- 1. Packer plugins (WCX)
  - 1.1. [[Pre-installed Plugins#^base64-wcx|Base64]]
  - 1.2. [[Pre-installed Plugins#^cpio-wcx|CPIO]]
  - 1.3. [[Pre-installed Plugins#^deb-wcx|DEB]]
  - 1.4. [[Pre-installed Plugins#^rpm-wcx|RPM]]
  - 1.5. [[Pre-installed Plugins#^sevenzip-wcx|SevenZip]]
  - 1.6. [[Pre-installed Plugins#^unrar-wcx|UnRAR]]
  - 1.7. [[Pre-installed Plugins#^zip-wcx|Zip]]
- 2. Content plugins (WDX)
  - 2.1. [[Pre-installed Plugins#^bexif|Built-in Exif plugin]]
  - 2.2. [[Pre-installed Plugins#^audioinfo-wdx|AudioInfo]]
  - 2.3. [[Pre-installed Plugins#^deb_wdx-wdx|DEB]]
  - 2.4. [[Pre-installed Plugins#^rpm_wdx-wdx|RPM]]
  - 2.5. [[Pre-installed Plugins#^lscripts|Lua scripts]]
- 3. File system plugins (WFX)
  - 3.1. [[Pre-installed Plugins#^ftp-wfx|FTP]]
  - 3.2. [[Pre-installed Plugins#^maccloud-wfx|MacCloud]]<sup>(Alpha version)</sup>
- 4. Lister plugins (WLX)
  - 4.1. [[Pre-installed Plugins#^macpreview-wlx|MacPreview]]
  - 4.2. [[Pre-installed Plugins#^preview-wlx|Explorer Preview]]
  - 4.3. [[Pre-installed Plugins#^richview-wlx|Rich Text Format]]
  - 4.4. [[Pre-installed Plugins#^wlxmplayer-wlx|WlxMplayer]]
  - 4.5. [[Pre-installed Plugins#^wmp-wlx|Windows Media Player]]
- 5. Search plugin (DSX)
  - 5.1. [[Pre-installed Plugins#^dsxlocate-dsx|DSXLocate]]

## 1. Packer plugins (WCX)

**Base64** ^base64-wcx

The Base64 plugin provides the ability to encode and decode files according to the Base64 scheme, this is one of the standards for encoding binary data using printable ASCII characters.

**CPIO** ^cpio-wcx

Packer plugin for unpacking CPIO archives.

**DEB** ^deb-wcx

Packer plugin for unpacking the package files of the dpkg package management system (Debian and distributions based on it).

Linux and other Unix-like OS (in Windows, Double Commander uses the [[Pre-installed Plugins#^sevenzip-wcx|SevenZip]] plugin for this format).

**RPM** ^rpm-wcx

Packer plugin for unpacking the package files of the Red Hat package management system (Red Hat Linux, SUSE Linux and others).

**SevenZip** ^sevenzip-wcx

Packer plugin for working with .7z, .arj, .cab, .cpio, .cramfs, .deb, .dmg, .fat, .hfs, .iso, .lha, .lzh, .ntfs, .squashfs, .taz, .vhd, .wim, .xar and .z files. We can also add other file types that are supported by 7-Zip.

Note: Some formats are read-only, meaning only content viewing, unpacking, and testing are available.

Windows only.

**UnRAR** ^unrar-wcx

Packer plugin for unpacking RAR archives.

For using this plugin we need the [UnRAR](https://www.rarlab.com/) library, the plugin will use `unrar.dll` (Windows), `libunrar.dylib` (macOS), `libunrar.so` or `libunrar.so.5` (Linux and other Unix-like OS).

The distributions of Double Commander for Windows and the portable versions for Linux contain the necessary library, in other cases, we can use the usual ways to get libraries in the operating system (for example, package `libunrar5` in Debian/Ubuntu or `libunrar` in Arch Linux). Otherwise, we can try to find a suitable variant on [this](https://www.rarlab.com/rar_add.htm) page (the file must be copied to the system directory or the directory where the Double Commander executable file is located).

The plugin also supports the ability to pack files into a RAR archive, to do this, we need to specify the path to `WinRAR.exe` (Windows only) or the `rar` command line utility in the plugin settings.

**Zip** ^zip-wcx

Packer plugin for working with .bz2, .gz, .jar, .lzma, .tar, .tbz, .tgz, .tlz, .txz, .tzst, .xz, .zip, .zipx and .zst archives. Also this plugin can open files based on ZIP (EPUB, Office Open XML, OpenDocument format, CRX, XPI and others).

Requires additional compressor libraries:

- bzip2: `bz2.dll` (Windows), `libbz2.dylib` (macOS), `libbz2.so.1` (Linux and other Unix-like OS).
- XZ: `liblzma.dll` (Windows), `liblzma.dylib` (macOS), `liblzma.so.5` (Linux and other Unix-like OS).
- Zstandard: `libzstd.dll` (Windows), `libzstd.dylib` (macOS), `libzstd.so.1` (Linux and other Unix-like OS).

The distributions of Double Commander for Windows contain all necessary libraries and these libraries are usually installed by default in Linux for desktop/workstations.

## 2. Content plugins (WDX)

**Built-in Exif plugin** ^bexif

The program has a built-in Exif content plugin to get some data that can be stored in the metadata of JPEG files: date, pixel dimensions, image orientation and camera information.

JPEG images only.

**AudioInfo** ^audioinfo-wdx

This content plugin shows information about audio files, technical (duration, bitrate, number of channels and so on) and metadata (title, artist and other).

The following types of metadata are supported: ID3v1 (1.0, 1.1), ID3v2 (2.2, 2.3, 2.4), APE (1.0, 2.0), Vorbis comment.

**DEB** ^deb_wdx-wdx

This content plugin shows information about the package files of the dpkg package management system (Debian and distributions based on it): package name, version, description, dependencies and other.

**RPM** ^rpm_wdx-wdx

This content plugin shows information about the package files of the Red Hat package management system (Red Hat Linux, SUSE Linux and others): package name, version, description and other.

**Lua scripts** ^lscripts

The `plugins/wdx/scripts` directory contains several examples of content plugins written in Lua (see the [[Lua Scripting|Lua scripting]] help page for details).

These plugins are not added in the program settings.

- `descriptionwdx.lua` – reads file descriptions from `descript.ion`.
- `fulltextodtwdx.lua` – finds text in OpenDocument Text files (ODT). Requires `odt2txt`.
- `simplewdx.lua` – simple example with several fields.
- `textlinewdx.lua` – returns the first lines of plain text files (.txt, .ini) one by one, from the first to the fifth.

## 3. File system plugins (WFX)

**FTP** ^ftp-wfx

This is a file system plugin for working with the following network protocols: FTP, FTPS, FTPES, SFTP and SSH+SCP. The plugin also supports working with proxy servers (HTTP, SOCKS 4 or SOCKS 5).

Requires additional libraries:

1) SSL and TLS protocols

The [OpenSSL](https://www.openssl.org/) cryptographic library (3.1, 3.0, 1.1.1, 1.1.0, 1.0.2, 1.0.1):

- Windows: plugin contains a list of common names, and the required files will be found automatically.
- macOS: `libssl.N.dylib` and `libcrypto.N.dylib` (where "N" is a version number) or `libssl.dylib` and `libcrypto.dylib`.
- Linux and other Unix-like OS: `libssl.so.N` and `libcrypto.so.N`, where "N" is a version number.

Compiled OpenSSL binaries for Windows can be found [here](https://wiki.openssl.org/index.php/Binaries), in other cases, we can use the operating system's package manager (for example, package `libssl3` or `libssl1.1` in Debian/Ubuntu, `openssl` in Arch Linux, `openssl` in macOS (Homebrew)).

Note: In Windows, libraries must be located near the Double Commander executable file or in the Windows system directory.

Alternatively, in Linux, the plugin can use the [GnuTLS](https://www.gnutls.org/) library (`libgnutls.so.N`, where "N" is a version number).

2) SSH protocol

The [libssh](https://libssh2.org/) library: the FTP plugin will use `libssh2.dll` (Windows), `libssh2.dylib` (macOS) or `libssh2.so.1` (Linux and other Unix-like OS).

The distributions of Double Commander for Windows contain this library, in other cases, we can use the usual ways to get libraries in the operating system (for example, package `libssh2-1` in Debian/Ubuntu, `libssh2` in Arch Linux, `libssh2` in macOS (Homebrew)).

Plugin allows to use an SSH authentication agent (for example, ssh-agent from the OpenSSH utility suite, Pageant from PuTTY).

**MacCloud**<sup>(Alpha version)</sup> ^maccloud-wfx

Offical cloud plugin for macOS, it supports:

- DropBox
- Yandex
- One Drive
- Box
- Amazon S3
- BackBlaze B2
- Alibaba Cloud OSS
- Tencent Cloud COS
- Huawei Cloud OBS
- Qiniu KODO
- Upyun USS
- S3 Compatible

macOS only.

## 4. Lister plugins (WLX)

**MacPreview** ^macpreview-wlx

Universal (office document formats, images, video and audio files, and more) plugin using [Quick Look](https://en.wikipedia.org/wiki/Quick_Look), as in Finder.

macOS only.

**Explorer Preview** ^preview-wlx

Plugin for the display of rich preview. The IPreviewHandler interface supports many formats (depends on the version of the operating system and installed applications), by default, only HTML files are added to the detect string.

Note: Preview handlers may not display all the information contained in the file.

Windows only.

**Rich Text Format** ^richview-wlx

Plugin for viewing RTF files.

Windows only.

**WlxMplayer** ^wlxmplayer-wlx

Plugin for viewing video files. Requires `mplayer`.

Linux only.

**Windows Media Player** ^wmp-wlx

Plugin for playing audio and video files. This plugin uses the IWMPPlayer4 interface (ActiveX), requires Windows Media Player 9 or later.

Windows only.

## 5. Search plugin (DSX)

**DSXLocate** ^dsxlocate-dsx

This plugin uses `locate` and its file database for searching. We can search by file name, part of it or by mask (symbol "*" means match any number of characters).

Linux and other Unix-like OS.

---

[[Indice|← Index]]
