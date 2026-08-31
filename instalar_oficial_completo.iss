; ==============================================================
; Inno Setup - Instalador Oficial Completo (Oficina de Pesca)
; Saida final: Output\Instalador_Oficina_Pesca_Oficial.exe
; ==============================================================

#define AppName "Oficina de Pesca versão {#AppVersion} - Instalador"
#define AppVersion "1.0.57"
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
OutputBaseFilename=Instalador_Oficina_Pesca_Oficial_v1.0.57
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
SetupIconFile=assets\logo.ico
LicenseFile=Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf
; Diálogo de idioma desativado: o idioma é selecionado automaticamente
; conforme o idioma configurado no Windows do usuário.
ShowLanguageDialog=no

[Languages]
; O contrato (LicenseFile) acompanha o idioma selecionado automaticamente
; pelo Windows: português (Brasil), inglês (EUA) ou espanhol (fallback pt_BR).
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf"
Name: "english"; MessagesFile: "compiler:Default.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"; LicenseFile: "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; Executavel onefile gerado pelo PyInstaller
Source: "dist\Oficina_Pesca\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Recursos visuais (logo, icones e assets)
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\*"; DestDir: "{app}\_internal\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\fundo_menu.jpeg"; DestDir: "{app}\_internal\assets"; Flags: ignoreversion skipifsourcedoesntexist

; Imagens de fundo e logo na raiz do app
Source: "fundomenu.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "LOGO.bmp"; DestDir: "{app}"; Flags: ignoreversion
Source: "icone_app_chave_anzol.png"; DestDir: "{app}"; Flags: ignoreversion

; Configuracao padrao na raiz (evita aviso de URL publica ausente)
Source: "config.cfg"; DestDir: "{app}"; Flags: ignoreversion
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal"; Flags: ignoreversion skipifsourcedoesntexist
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal\assets"; Flags: ignoreversion skipifsourcedoesntexist

; APK Android assinado dentro da pasta apk_celular_distribuicao
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\apk_celular_distribuicao"; DestName: "oficina_app.apk"; Flags: ignoreversion
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\_internal\apk_celular_distribuicao"; DestName: "oficina_app.apk"; Flags: ignoreversion
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\_internal\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist

; Documentos de contrato e termos de uso
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist
Source: "termos_de_uso.txt"; DestDir: "{app}\Documentos"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\logo.ico"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\logo.ico"; Tasks: desktopicon
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
