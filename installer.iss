; Inno Setup script (https://jrsoftware.org/isinfo.php) - optional single-file installer
[Setup]
AppName=Knowledge Vault
AppVersion=1.0.0
DefaultDirName={autopf}\KnowledgeVault
DefaultGroupName=Knowledge Vault
OutputBaseFilename=KnowledgeVault-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\KnowledgeVault\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Knowledge Vault"; Filename: "{app}\KnowledgeVault.exe"
Name: "{autodesktop}\Knowledge Vault"; Filename: "{app}\KnowledgeVault.exe"
