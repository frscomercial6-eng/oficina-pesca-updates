; ==============================================================
;  Inno Setup Script - Oficina de Pesca
;  Requisito: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
;  Como usar:
;    1. Execute: pyinstaller oficina.spec
;    2. Abra este arquivo no Inno Setup Compiler (ou ISCC.exe)
;    3. Pressione F9 para compilar
;    4. O instalador sera gerado em: INSTALADOR_FINAL\Instalador_Oficina_Pesca.exe
; ==============================================================
#define AppVersion "1.0.27"
#define AppName "Oficina de Pesca"
#define AppPublisher "FRS Solucoes"
#define AppExeName "Oficina_Pesca.exe"
#define SourceDir "dist\Oficina_Pesca"
#define LicenseSecret "ALTERAR-EM-PRODUCAO"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={commonpf32}\Oficina de Pesca
DefaultGroupName={#AppName}
UsePreviousAppDir=no
DisableDirPage=yes
AllowNoIcons=yes

OutputDir=INSTALADOR_FINAL
OutputBaseFilename=Setup_OficinaPesca_v1.0.27
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile=Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf
ShowLanguageDialog=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ChangesEnvironment=yes
SetupIconFile=icone_oficina.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"; Flags: checkedonce

[InstallDelete]
; Limpeza de instalações legadas antes de copiar a nova versão.
Type: filesandordirs; Name: "{commonpf32}\OficinaPesca"
Type: filesandordirs; Name: "{autopf}\OficinaPesca"
Type: filesandordirs; Name: "{commonpf}\OficinaPesca"
Type: filesandordirs; Name: "{app}"

[Files]
; Todos os arquivos gerados pelo PyInstaller (excluindo .env para nao expor credenciais)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env,apk_celular_distribuicao\*,oficina.db"
; Apenas os dois arquivos de distribuicao mobile (APK assinado + instrucoes)
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\_internal\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\_internal\apk_celular_distribuicao"; Flags: ignoreversion skipifsourcedoesntexist
; Imagens de fundo do menu
Source: "fundomenu.png";      DestDir: "{app}"; Flags: ignoreversion
Source: "LOGO.bmp";          DestDir: "{app}"; Flags: ignoreversion
Source: "icone_oficina.ico"; DestDir: "{app}"; Flags: ignoreversion
; Servidor web (acesso por celular/rede)
Source: "servidor.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "config.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "config.cfg";           DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "config.json";          DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "versao.json";          DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "iniciar_servidor.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal"; Flags: ignoreversion skipifsourcedoesntexist
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal\assets"; Flags: ignoreversion skipifsourcedoesntexist
Source: "templates\*";          DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*";             DestDir: "{app}\static";    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "instala\ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"; DestDir: "{app}\instala"; Flags: ignoreversion
[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icone_oficina.ico"
Name: "{group}\Iniciar Servidor Web"; Filename: "{app}\iniciar_servidor.bat"; Comment: "Inicia o servidor para acesso via rede e celular"
Name: "{group}\Desinstalar";          Filename: "{uninstallexe}"
Name: "{commondesktop}\Oficina de Pesca";   Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icone_oficina.ico"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: string; ValueName: "OFP_LICENCA_SECRET"; ValueData: "{#LicenseSecret}"; Flags: uninsdeletevalue

[Code]
procedure LimparRegistroLegado();
begin
	RegDeleteKeyIncludingSubkeys(HKCU, 'Software\\OficinaPesca');
	RegDeleteKeyIncludingSubkeys(HKLM, 'Software\\OficinaPesca');
	RegDeleteKeyIncludingSubkeys(HKLM, 'SOFTWARE\\WOW6432Node\\OficinaPesca');
	RegDeleteKeyIncludingSubkeys(HKLM, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Oficina de Pesca_is1');
	RegDeleteKeyIncludingSubkeys(HKLM, 'SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Oficina de Pesca_is1');
	RegDeleteKeyIncludingSubkeys(HKLM, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Oficina de Pesca versão 1.0.9 - Instalador_is1');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
	if CurStep = ssInstall then
		LimparRegistroLegado();
end;

[Run]
Filename: "{app}\{#AppExeName}";        Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\instala\ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"; Parameters: "/VERYSILENT"; Flags: nowait postinstall skipifsilent
