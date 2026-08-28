# Organização inicial para limpeza do projeto

## Passo 1 - isolar funções de licença, backup e sincronização

### Objetivo
Separar responsabilidades do menu.py para módulos em core/.

### Arquivos criados
- core/licenca.py
- core/sincronizacao.py

### Ajuste aplicado
- menu.py passou a usar helpers em core para a lógica de licença e checagem de Firebase.

## Passo 2 - mover artefatos de infraestrutura/build para infra/

### Arquivos e pastas recomendados para mover
- build_final_setup.bat
- build_final_setup_trace.txt
- deploy_cloud_run.bat
- gerar_instalador_final.bat
- gerar_release.bat
- publicar_app_com_api.bat
- iniciar_servidor.bat
- mestre_build.py
- version_info.py
- version.json / versao.json / versao.txt / version.txt
- build/
- dist/
- Output/
- PACOTE_ENVIO/
- INSTALADOR_FINAL/
- instalador .iss e arquivos de empacotamento

### Estratégia
- Manter o código fonte em raiz apenas para módulos principais.
- Guardar artefatos de build, distribuição e deployment em infra/.

## Passo 3 - reorganizar arquivos de suporte

### Futuras migrações recomendadas
- mover scripts utilitários para tools/ ou infra/deploy/
- mover arquivos de configuração sensível para config/ ou secrets/
- manter templates/, static/, assets/ e tests/ no lugar atual
