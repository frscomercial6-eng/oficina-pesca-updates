Set-Location 'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL'
Write-Host 'Criando .venv_build...'
py -3.11 -m venv '.\.venv_build'
 = '.\.venv_build\\Scripts\\python.exe'
&  -m pip install --upgrade pip setuptools wheel --quiet
&  -m pip install -r '.\requirements.txt' --quiet
&  -m pip install 'pyinstaller==6.22.2' --quiet
&  --version
&  -m PyInstaller --version
&  -c 'import ast; [ast.parse(open(f,encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(46)).read()) for f in [chr(39)+chr(109)+chr(101)+chr(110)+chr(117)+chr(46)+chr(112)+chr(121),chr(39)+chr(116)+chr(101)+chr(108)+chr(97)+chr(95)+chr(111)+chr(115)+chr(46)+chr(112)+chr(121),chr(39)+chr(109)+chr(101)+chr(115)+chr(116)+chr(114)+chr(101)+chr(95)+chr(98)+chr(117)+chr(105)+chr(108)+chr(100)+chr(46)+chr(112)+chr(121)]]; print(chr(65)+chr(83)+chr(84)+chr(95)+chr(79)+chr(75))'
Write-Host 'DONE'
