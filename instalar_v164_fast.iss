; ==============================================================
; Inno Setup - Instalador v1.0.64 (Fast)
; ==============================================================

#define AppName "Oficina de Pesca"
#define AppVersion "1.0.64"
#define AppPublisher "FRS Solutions"
#define AppExeName "Oficina_Pesca.exe"

[Setup]
AppId={{8C0E60A5-6403-4EDB-92A4-0890E589A8F1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\OficinaPesca
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=Instalador_Oficina_Pesca_v1.0.64_fast
Compression=lzma
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
ShowLanguageDialog=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\Oficina_Pesca\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent