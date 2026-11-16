param(
    [ValidateSet('start','setup','test','update','status')][string]$Action = 'start',
    [ValidateRange(1024,65535)][int]$Port = 8501,
    [string]$Python = '',
    [switch]$Completo,
    [switch]$UsarPip
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
foreach($folder in @('.cache/tmp','.cache/pip','.cache/uv','.cache/python','.cache/pytest')){
    [IO.Directory]::CreateDirectory((Join-Path $root $folder)) | Out-Null
}
$env:TEMP=Join-Path $root '.cache/tmp'
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $root '.cache/pip'
$env:UV_CACHE_DIR=Join-Path $root '.cache/uv'
$env:PYTHONUTF8='1'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS='false'
if(Test-Path -LiteralPath 'D:\Ferramentas\Python\uv-managed'){
    $env:UV_PYTHON_INSTALL_DIR='D:\Ferramentas\Python\uv-managed'
}
$venv=Join-Path $root '.venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $venv)){
    $candidates=@()
    if($Python){$candidates+=@{Command=$Python;Arguments=@()}}
    $systemPython=Get-Command python.exe -ErrorAction SilentlyContinue
    if($systemPython -and $systemPython.Source -notlike '*WindowsApps*'){
        $candidates+=@{Command=$systemPython.Source;Arguments=@()}
    }
    if(Get-Command py.exe -ErrorAction SilentlyContinue){
        $candidates+=@{Command='py';Arguments=@('-3.13')}
        $candidates+=@{Command='py';Arguments=@('-3.12')}
    }
    if(Get-Command uv.exe -ErrorAction SilentlyContinue){
        $managed=& uv python find 3.13 --no-python-downloads 2>$null
        if($LASTEXITCODE -eq 0){$candidates+=@{Command=([string]$managed).Trim();Arguments=@()}}
    }
    $created=$false
    foreach($candidate in $candidates){
        $command=$candidate.Command
        $arguments=$candidate.Arguments
        & $command @arguments -c 'import sys;sys.exit(0 if (3,12)<=sys.version_info[:2]<(3,14) else 1)' 2>$null
        if($LASTEXITCODE -ne 0){continue}
        & $command @arguments -m venv .venv
        if($LASTEXITCODE -eq 0){$created=$true;break}
    }
    if(-not $created){throw 'Instale Python 3.12 ou 3.13. Consulte README.md; pode informar -Python com o caminho completo.'}
}
& $venv -c 'import sys;sys.exit(0 if (3,12)<=sys.version_info[:2]<(3,14) else 1)'
if($LASTEXITCODE -ne 0){throw 'O ambiente requer Python 3.12 ou 3.13.'}
$requirements=if($Action -eq 'test'){'requirements-dev.txt'}else{'requirements.txt'}
$kind=if($Action -eq 'test'){'test'}else{'runtime'}
$stamp=Join-Path $root ('.cache/dependencies-'+$kind+'.sha256')
$signature=& $venv -c 'import hashlib,pathlib,sys;print(hashlib.sha256(bytes().join(pathlib.Path(p).read_bytes() for p in sys.argv[1:])).hexdigest())' $requirements 'pyproject.toml'
if($LASTEXITCODE -ne 0){throw 'Falha ao conferir as dependencias.'}
$prepared=(Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $signature)
if(-not $prepared){
    if((-not $UsarPip) -and (Get-Command uv.exe -ErrorAction SilentlyContinue)){
        & uv pip install --python $venv -r $requirements
        if($LASTEXITCODE -ne 0){throw 'Falha ao instalar as dependências fixadas.'}
        & uv pip install --python $venv --no-deps -e .
    }else{
        & $venv -m pip install -r $requirements
        if($LASTEXITCODE -ne 0){throw 'Falha ao instalar as dependências fixadas.'}
        & $venv -m pip install --no-deps -e .
    }
    if($LASTEXITCODE -ne 0){throw 'Falha ao preparar o projeto.'}
    [IO.File]::WriteAllText($stamp,$signature)
}
switch($Action){
    'setup' {Write-Output 'Pronto. Use iniciar.cmd ou testar.cmd.';exit 0}
    'test' {
        & $venv -m ruff check src tests app.py
        if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
        & $venv -m pytest '--basetemp=.cache/pytest'
    }
    'update' {
        if($Completo){& $venv -m radar_inflacao update --full}else{& $venv -m radar_inflacao update}
    }
    'status' {& $venv -m radar_inflacao status}
    'start' {
        Write-Output ('Abra http://localhost:'+$Port+' no navegador. Ctrl+C encerra.')
        & $venv -m streamlit run app.py "--server.port=$Port" --server.address=127.0.0.1 --server.headless=true --browser.gatherUsageStats=false
    }
}
exit $LASTEXITCODE
