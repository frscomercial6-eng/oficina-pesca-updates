; ==============================================================
; Inno Setup - Instalador v1.0.64
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
OutputBaseFilename=Instalador_Oficina_Pesca_v1.0.64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
ShowLanguageDialog=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf"
Name: "english"; MessagesFile: "compiler:Default.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; Executavel
Source: "dist\Oficina_Pesca\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Oficina_Pesca\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Recursos visuais
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "fundomenu.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LOGO.bmp"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "icone_app_chave_anzol.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Configuracao
Source: "config.cfg"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "versao.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "version.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "client_secret_desktop.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Documentos
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent