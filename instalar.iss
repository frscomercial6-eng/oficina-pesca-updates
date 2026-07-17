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
#define AppVersion "1.0.48"
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
DefaultDirName={localappdata}\Oficina de Pesca
DefaultGroupName={#AppName}
UsePreviousAppDir=yes
DisableDirPage=yes
AllowNoIcons=yes

OutputDir=INSTALADOR_FINAL
OutputBaseFilename=Setup_OficinaPesca_v1.0.48
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile=Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf
ShowLanguageDialog=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
SetupIconFile=icone_oficina.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Components]
Name: "core"; Description: "Sistema Oficina de Pesca (obrigatório)"; Types: full custom; Flags: fixed
Name: "acbrmonitor"; Description: "Instalar ACBrMonitorPLUS (necessário para emissão de notas)"; Types: full custom; Check: DevePreSelecionarACBr

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"; Flags: checkedonce

[InstallDelete]
; Mantido intencionalmente sem remoções destrutivas para preservar banco e perfil do cliente.

[Files]
; Todos os arquivos gerados pelo PyInstaller (excluindo .env para nao expor credenciais)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Components: core; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env,apk_celular_distribuicao\*,*.db,config.cfg,config.json,versao.json,licenca.key,licenca.json,licencas.json"
; Apenas os dois arquivos de distribuicao mobile (APK assinado + instrucoes)
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\apk_celular_distribuicao"; Components: core; Flags: ignoreversion
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\apk_celular_distribuicao"; Components: core; Flags: ignoreversion skipifsourcedoesntexist
Source: "apk_celular_distribuicao\oficina_app_signed.apk"; DestDir: "{app}\_internal\apk_celular_distribuicao"; Components: core; Flags: ignoreversion
Source: "apk_celular_distribuicao\instrucoes_instalacao.txt"; DestDir: "{app}\_internal\apk_celular_distribuicao"; Components: core; Flags: ignoreversion skipifsourcedoesntexist
; Imagens de fundo do menu
Source: "fundomenu.png";      DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "LOGO.bmp";          DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "icone_oficina.ico"; DestDir: "{app}"; Components: core; Flags: ignoreversion
; Servidor web (acesso por celular/rede)
Source: "servidor.py";          DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "config.py";            DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "config.cfg";           DestDir: "{app}"; Components: core; Flags: ignoreversion onlyifdoesntexist
Source: "config.json";          DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "versao.json";          DestDir: "{app}"; Components: core; Flags: ignoreversion onlyifdoesntexist
Source: "iniciar_servidor.bat"; DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "Atualizador.exe";      DestDir: "{app}"; Components: core; Flags: ignoreversion
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal"; Components: core; Flags: ignoreversion skipifsourcedoesntexist
Source: "client_secret_desktop.json"; DestDir: "{app}\_internal\assets"; Components: core; Flags: ignoreversion skipifsourcedoesntexist
; Garante recursos visuais também no bundle interno (compatível com runtime _internal/assets)
Source: "assets\*";             DestDir: "{app}\_internal\assets"; Components: core; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\fundo_menu.jpeg"; DestDir: "{app}\_internal\assets"; Components: core; Flags: ignoreversion skipifsourcedoesntexist
Source: "templates\*";          DestDir: "{app}\templates"; Components: core; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*";             DestDir: "{app}\static";    Components: core; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "instala\ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"; DestDir: "{app}\instala"; Components: acbrmonitor; Flags: ignoreversion
[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icone_oficina.ico"
Name: "{group}\Iniciar Servidor Web"; Filename: "{app}\iniciar_servidor.bat"; Comment: "Inicia o servidor para acesso via rede e celular"
Name: "{group}\Desinstalar";          Filename: "{uninstallexe}"
Name: "{userdesktop}\Oficina de Pesca";   Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icone_oficina.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}";        Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\instala\ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"; Parameters: "/VERYSILENT"; Check: DeveExecutarInstalacaoACBr; Flags: waituntilterminated postinstall skipifsilent

[Code]
var
	DetectadoACBrPath: string;
	ConfirmouModoSemNota: Boolean;
	TratandoClickComponente: Boolean;

function EscapeJson(const S: string): string;
var
	T: string;
begin
	T := S;
	StringChangeEx(T, '\\', '\\\\', True);
	StringChangeEx(T, '"', '\\"', True);
	Result := T;
end;

function ArquivoACBrExiste(const PastaBase: string): Boolean;
begin
	Result :=
		FileExists(AddBackslash(PastaBase) + 'ACBrMonitor.exe') or
		FileExists(AddBackslash(PastaBase) + 'ACBrMonitorPLUS.exe');
end;

function EncontrarPastaACBrInstalada(): string;
var
	Candidato: string;
begin
	Result := '';

	Candidato := ExpandConstant('{commonpf32}\\ACBrMonitorPLUS');
	if DirExists(Candidato) and ArquivoACBrExiste(Candidato) then begin
		Result := Candidato;
		exit;
	end;

	Candidato := ExpandConstant('{commonpf}\\ACBrMonitorPLUS');
	if DirExists(Candidato) and ArquivoACBrExiste(Candidato) then begin
		Result := Candidato;
		exit;
	end;

	Candidato := ExpandConstant('{commonpf32}\\ACBrMonitor');
	if DirExists(Candidato) and ArquivoACBrExiste(Candidato) then begin
		Result := Candidato;
		exit;
	end;

	Candidato := ExpandConstant('{commonpf}\\ACBrMonitor');
	if DirExists(Candidato) and ArquivoACBrExiste(Candidato) then begin
		Result := Candidato;
		exit;
	end;

	Candidato := 'C:\\ACBrMonitorPLUS';
	if DirExists(Candidato) and ArquivoACBrExiste(Candidato) then begin
		Result := Candidato;
		exit;
	end;
end;

function DetectarACBrJaInstalado(): Boolean;
begin
	if DetectadoACBrPath = '' then
		DetectadoACBrPath := EncontrarPastaACBrInstalada();
	Result := DetectadoACBrPath <> '';
end;

function DevePreSelecionarACBr(): Boolean;
begin
	Result := not DetectarACBrJaInstalado();
end;

function DeveExecutarInstalacaoACBr(): Boolean;
begin
	Result := WizardIsComponentSelected('acbrmonitor') and (not DetectarACBrJaInstalado());
end;

function PastaMonitorConfigurada(): string;
begin
	if DetectarACBrJaInstalado() then begin
		Result := DetectadoACBrPath;
		exit;
	end;

	if WizardIsComponentSelected('acbrmonitor') then begin
		Result := ExpandConstant('{commonpf32}\\ACBrMonitorPLUS');
		exit;
	end;

	Result := ExpandConstant('{app}\\config_fiscal\\acbr_monitor');
end;

procedure GravarArquivosConfiguracaoFiscal();
var
	PastaCfg: string;
	PastaMonitor: string;
	ArquivoEntrada: string;
	ArquivoSaida: string;
	ArquivoIni: string;
	JsonPath: string;
	SetupTxtPath: string;
	JsonConteudo: string;
	IniConteudo: string;
	SetupConteudo: string;
begin
	PastaCfg := ExpandConstant('{app}\\config_fiscal');
	PastaMonitor := PastaMonitorConfigurada();
	ArquivoEntrada := AddBackslash(PastaMonitor) + 'ENT.txt';
	ArquivoSaida := AddBackslash(PastaMonitor) + 'SAI.txt';
	ArquivoIni := AddBackslash(PastaCfg) + 'acbrlib.ini';
	JsonPath := AddBackslash(PastaCfg) + 'config_fiscal.json';
	SetupTxtPath := AddBackslash(PastaCfg) + 'acbr_monitor_setup.txt';

	ForceDirectories(PastaCfg);
	if not DetectarACBrJaInstalado() then
		ForceDirectories(PastaMonitor);

	JsonConteudo :=
		'{' + #13#10 +
		'  "provedor": "acbr",' + #13#10 +
		'  "acbr_modo": "monitor",' + #13#10 +
		'  "modalidade_fiscal": "nfe",' + #13#10 +
		'  "acbr_monitor_path": "' + EscapeJson(PastaMonitor) + '",' + #13#10 +
		'  "acbr_entrada": "' + EscapeJson(ArquivoEntrada) + '",' + #13#10 +
		'  "acbr_saida": "' + EscapeJson(ArquivoSaida) + '",' + #13#10 +
		'  "acbr_ini": "' + EscapeJson(ArquivoIni) + '"' + #13#10 +
		'}' + #13#10;
	SaveStringToFile(JsonPath, JsonConteudo, False);

	IniConteudo :=
		'[ACBrMonitor]' + #13#10 +
		'PastaMonitor=' + PastaMonitor + #13#10 +
		'ArquivoENT=' + ArquivoEntrada + #13#10 +
		'ArquivoSAI=' + ArquivoSaida + #13#10 + #13#10 +
		'[Fiscal]' + #13#10 +
		'Modalidade=nfe' + #13#10;
	SaveStringToFile(ArquivoIni, IniConteudo, False);

	SetupConteudo :=
		'CONFIGURACAO PADRAO ACBrMonitor' + #13#10 +
		'================================' + #13#10 +
		'Pasta monitor: ' + PastaMonitor + #13#10 +
		'ENT (entrada): ' + ArquivoEntrada + #13#10 +
		'SAI (saida): ' + ArquivoSaida + #13#10 +
		'INI ACBr: ' + ArquivoIni + #13#10 +
		'Modalidade fiscal: nfe' + #13#10;
	SaveStringToFile(SetupTxtPath, SetupConteudo, False);

	if (not WizardIsComponentSelected('acbrmonitor')) and ConfirmouModoSemNota then begin
		SaveStringToFile(
			ExpandConstant('{app}\\MODO_GESTAO_SEM_NOTA.txt'),
			'Modo de Gestão sem Nota ativo: o ACBrMonitorPLUS não foi instalado nesta máquina.' + #13#10,
			False
		);
	end;
end;

procedure TratarCliqueListaComponentes(Sender: TObject);
begin
	if TratandoClickComponente then
		exit;

	if WizardForm.CurPageID <> wpSelectComponents then
		exit;

	if WizardIsComponentSelected('acbrmonitor') then
		exit;

	TratandoClickComponente := True;
	try
		if MsgBox(
			'Atenção: A emissão de notas fiscais exige o ACBrMonitorPLUS instalado. Ao desmarcar esta opção, o sistema não poderá emitir notas. Deseja realmente prosseguir?',
			mbConfirmation,
			MB_YESNO or MB_DEFBUTTON2
		) = IDYES then begin
			ConfirmouModoSemNota := True;
		end else begin
			WizardSelectComponents('acbrmonitor');
			ConfirmouModoSemNota := False;
		end;
	finally
		TratandoClickComponente := False;
	end;
end;

function InitializeSetup(): Boolean;
begin
	DetectadoACBrPath := EncontrarPastaACBrInstalada();
	ConfirmouModoSemNota := False;
	TratandoClickComponente := False;
	Result := True;
end;

procedure InitializeWizard();
begin
	WizardForm.ComponentsList.OnClickCheck := @TratarCliqueListaComponentes;

	if DetectarACBrJaInstalado() then begin
		MsgBox(
			'ACBrMonitorPLUS já detectado em: ' + #13#10 + DetectadoACBrPath + #13#10#13#10 +
			'A instalação do ACBr será pulada e o instalador apenas configurará o caminho automaticamente.',
			mbInformation,
			MB_OK
		);
	end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
	if CurStep = ssPostInstall then begin
		GravarArquivosConfiguracaoFiscal();

		if (not WizardIsComponentSelected('acbrmonitor')) and ConfirmouModoSemNota then begin
			MsgBox(
				'Instalação concluída em Modo de Gestão sem Nota. O sistema continuará operando, mas a emissão fiscal ficará bloqueada até a instalação do ACBrMonitorPLUS.',
				mbInformation,
				MB_OK
			);
		end;
	end;
end;
