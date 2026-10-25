$ErrorActionPreference = 'Stop'

# 使い捨てのGitHub-hosted Windowsだけを対象とし、利用者PCやself-hostedには適用しない。
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
    $env:RUNNER_OS -ne 'Windows') {
    Write-Error 'CA repair requires a GitHub-hosted Windows runner' -ErrorAction Continue
    exit 2
}

# 証明書名やSHA-1 thumbprintではなく、Pythonの検査と同じ実DERのSHA-256を使う。
$AffectedFingerprint = '86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b'
$Hasher = [Security.Cryptography.SHA256]::Create()
$Disallowed = [Security.Cryptography.X509Certificates.X509Store]::new('Disallowed', 'LocalMachine')
$RemovedCount = 0
try {
    # 再取得されてもOSで信頼しないよう、一致した証明書だけを失効扱いのストアへ置く。
    $Disallowed.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    foreach ($Location in @('LocalMachine', 'CurrentUser')) {
        foreach ($StoreName in @('Root', 'CA')) {
            $Store = [Security.Cryptography.X509Certificates.X509Store]::new($StoreName, $Location)
            try {
                $Store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
                foreach ($Certificate in $Store.Certificates) {
                    $Fingerprint = -join ($Hasher.ComputeHash($Certificate.RawData) |
                        ForEach-Object { $_.ToString('x2') })
                    if ($Fingerprint -eq $AffectedFingerprint) {
                        # Pythonの既定Context列挙にも残らないよう、一致したコピーだけを除去する。
                        $Disallowed.Add($Certificate)
                        $Store.Remove($Certificate)
                        $RemovedCount++
                    }
                }
            } finally {
                $Store.Dispose()
            }
        }
    }
    Write-Output "Removed affected CA copies: $RemovedCount"
} catch {
    Write-Error "CI Windows CA preparation failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 2
} finally {
    $Disallowed.Dispose()
    $Hasher.Dispose()
}
