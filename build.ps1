param(
    [Parameter(Mandatory = $true)][string]$SourceRoot,
    [string]$NdkRoot,
    [string]$PythonExecutable = 'python',
    [string]$BashExecutable
)
$ErrorActionPreference = 'Stop'
$support = Join-Path $PSScriptRoot 'build-support'
if (-not $NdkRoot) {
    $NdkRoot = Join-Path $env:LOCALAPPDATA 'Android\Sdk\ndk\30.0.16248370'
}
if (-not $BashExecutable) {
    $gitCommand = (Get-Command git -ErrorAction Stop).Source
    $gitRoot = Split-Path (Split-Path $gitCommand -Parent) -Parent
    $BashExecutable = Join-Path $gitRoot 'usr\bin\bash.exe'
}
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$NdkRoot = (Resolve-Path -LiteralPath $NdkRoot).Path
$BashExecutable = (Resolve-Path -LiteralPath $BashExecutable).Path
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'src\GNUmakefile'))) {
    throw 'SourceRoot must point to the Termux PRoot checkout.'
}
if (-not ((Get-Content -LiteralPath (Join-Path $NdkRoot 'source.properties')) -match '^Pkg.Revision\s*=\s*30\.0\.16248370\s*$')) {
    throw 'This build recipe was verified with NDK 30.0.16248370.'
}
$archive = Join-Path $support 'downloads\talloc-2.5.0.tar.gz'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -ne '912AFA237510AE542A7733998EB18A12BCDA35AB6729C8E2DDB43E8D0EBAB007') {
    throw 'talloc source checksum mismatch.'
}
$extract = @'
import pathlib, sys, tarfile
assert sys.version_info >= (3, 11, 5), 'Python 3.11.5 or newer is required'
root = pathlib.Path(sys.argv[1])
if not (root / 'deps/talloc-2.5.0/talloc.c').is_file():
    with tarfile.open(root / 'downloads/talloc-2.5.0.tar.gz') as archive:
        archive.extractall(root / 'deps', filter='data')
'@
& $PythonExecutable -c $extract $support
if ($LASTEXITCODE -ne 0) { throw 'Source extraction failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $support 'talloc-config\default\config.h'))) {
    & $PythonExecutable (Join-Path $support 'configure_talloc.py') $NdkRoot $BashExecutable
    if ($LASTEXITCODE -ne 0) { throw 'talloc configuration failed; see build-support/talloc-configure.log.' }
}
& $PythonExecutable (Join-Path $support 'compile_proot.py') --source $SourceRoot --ndk $NdkRoot --shell $BashExecutable
if ($LASTEXITCODE -ne 0) { throw 'PRoot build failed; see build-support/compile.log.' }
$native = Join-Path $PSScriptRoot 'jniLibs\arm64-v8a'
New-Item -ItemType Directory -Path $native -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $support 'proot-arm64\proot') -Destination (Join-Path $native 'libproot.so') -Force
Copy-Item -LiteralPath (Join-Path $support 'proot-arm64\loader\loader') -Destination (Join-Path $native 'libproot_loader.so') -Force
$strip = Join-Path $NdkRoot 'toolchains\llvm\prebuilt\windows-x86_64\bin\llvm-strip.exe'
& $strip --strip-all (Join-Path $native 'libproot.so') (Join-Path $native 'libproot_loader.so')
if ($LASTEXITCODE -ne 0) { throw 'Stripping failed.' }
Write-Output 'Build finished. ARM64 executable files are in jniLibs/arm64-v8a.'
Write-Output 'Existing verification.json describes the originally delivered binaries; regenerate checks after rebuilding.'
