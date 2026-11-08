# Wololo Mobile

Apps nativos para iOS 17+ e Android 8+. A interface fica em inglês.

## Identificadores

| Componente | Identificador |
| --- | --- |
| App iOS e Android | `dev.edilson.wololo` |
| Share Extension iOS | `dev.edilson.wololo.share` |
| App Group | `group.dev.edilson.wololo` |
| Apple Developer Team pessoal | `5T3LZC3A68` |
| App Store Connect Apple ID | `6832327047` |
| App Store Connect SKU | `wololo-ios` |

## Build local

O projeto Xcode contém o app, a extensão e o pacote local WololoKit.

```sh
cd mobile/ios/Packages/WololoKit
swift test
cd ../..
xcodebuild -project Wololo.xcodeproj -scheme Wololo \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Para instalar no iPhone, abra `mobile/ios/Wololo.xcodeproj`, selecione a equipe pessoal em Signing & Capabilities para os dois targets e escolha o aparelho. A assinatura automática precisa de acesso ao portal da Apple e de um aparelho cadastrado.

```sh
cd mobile/android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

O Android usa Java 17 ou superior e Android SDK 35. O APK de desenvolvimento fica em `app/build/outputs/apk/debug/`. O build release usa R8 e as variáveis `WOLOLO_KEYSTORE_FILE`, `WOLOLO_KEYSTORE_PASSWORD`, `WOLOLO_KEY_ALIAS` e `WOLOLO_KEY_PASSWORD`.

## GitHub Actions

O workflow **Mobile** testa WololoKit, compila os targets iOS para simulador e dispositivo, executa testes e lint Android e gera APKs. Ele roda em pushes, pull requests e nas releases.

O workflow **Release** publica a versão do servidor/site e anexa o APK Android assinado. Os apps têm versão própria, inicialmente 1.0.0.

O workflow **iOS Distribution** é manual e exporta um IPA para TestFlight ou Ad Hoc. As credenciais abaixo habilitam a assinatura no CI. O build de simulador e a validação do archive funcionam antes dessa configuração.

## Certificados e secrets do iOS

1. Os App IDs `dev.edilson.wololo` e `dev.edilson.wololo.share`, o App Group `group.dev.edilson.wololo` e o registro do app no App Store Connect já foram criados na equipe pessoal. Mantenha esses identificadores nos profiles.
2. No Acesso às Chaves do Mac, localize o certificado **Apple Distribution da sua equipe pessoal**, junto da chave privada. Exporte somente essa identidade como `.p12` e defina uma senha.
3. Crie um provisioning profile para cada App ID usando o mesmo certificado. Para TestFlight, escolha App Store Connect. Para Ad Hoc, escolha Ad Hoc e inclua os UDIDs dos iPhones. Ambos precisam conter o App Group e os entitlements do projeto.
4. No GitHub, abra o repositório, Settings, Secrets and variables, Actions. Cadastre a variável `IOS_TEAM_ID` com `5T3LZC3A68`.
5. Cadastre os secrets da tabela. Os arquivos são codificados em Base64 antes de serem colados no campo do GitHub.

| Secret | Conteúdo |
| --- | --- |
| `IOS_CERTIFICATE_BASE64` | Arquivo `.p12` em Base64 |
| `IOS_CERTIFICATE_PASSWORD` | Senha do `.p12` |
| `IOS_APP_PROFILE_BASE64` | Profile do app em Base64 |
| `IOS_SHARE_PROFILE_BASE64` | Profile da extensão em Base64 |
| `ASC_KEY_ID` | Key ID da API key do App Store Connect |
| `ASC_ISSUER_ID` | Issuer ID da equipe no App Store Connect |
| `ASC_PRIVATE_KEY_BASE64` | Arquivo privado `.p8` em Base64 |

Para copiar um arquivo como Base64 no Mac, execute `base64 -i /caminho/do/arquivo | pbcopy`. A codificação serve para transportar o arquivo. O armazenamento seguro fica a cargo do GitHub Actions Secrets.

Para obter a API key, abra App Store Connect, Users and Access, Integrations, App Store Connect API. Crie uma Team API key com permissão de upload, por exemplo App Manager, e baixe a `.p8`. O registro iOS do Wololo já existe no App Store Connect com Apple ID `6832327047` e SKU `wololo-ios`. Use esse registro para os próximos uploads.

Depois, em Actions, selecione **iOS Distribution**, escolha a referência da release e execute **Run workflow**. Use `app-store-connect` com os profiles de TestFlight e marque `upload_testflight` para enviar o build. Use `ad-hoc` com os profiles Ad Hoc para gerar um IPA destinado aos aparelhos cadastrados. O número do build usa 100 mais o número da execução do workflow, reservando os primeiros números para builds locais.

O certificado e sua chave privada assinam o app. A API key autentica o envio ao App Store Connect. O processamento e a disponibilidade do build no TestFlight podem demorar após o upload.

## Assinatura do Android

A chave de assinatura do Wololo foi criada fora do repositório, em `~/.config/wololo/signing/wololo-android.jks`. As credenciais locais ficam em `android-signing.json` nessa pasta, com acesso restrito ao usuário. Guarde uma cópia de segurança desses dois arquivos para assinar futuras atualizações do mesmo app.

Os secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` e `ANDROID_KEY_PASSWORD` estão configurados no repositório. A release utiliza essa identidade estável para gerar o APK instalável.

## Configuração e uso

Abra o app uma vez para conferir o servidor, a qualidade padrão e as permissões. O servidor padrão é `https://wololo.edilson.dev`. Uma chave pode ser configurada quando o servidor tiver `API_KEYS` habilitado.

Compartilhe um link para Wololo e escolha MP4 ou MP3. Vídeos são salvos em Fotos no iOS e Movies/Wololo no Android. O Android salva áudio em Music/Wololo. No iOS, o app expõe sua pasta Documents em Arquivos, e a extensão pode exportar o áudio pelo seletor de documentos.

O iOS pode encerrar a extensão. A transferência de um arquivo pronto usa uma sessão em segundo plano. Se a extensão fechar enquanto o servidor ainda processa, o app retoma o job quando for aberto. A fila compartilhada mantém esse estado. Uma transferência em background também depende das decisões de agendamento do sistema.

Os testes automatizados usam respostas controladas. A validação final no aparelho precisa incluir compartilhamento a partir de outro app, permissões, rede interrompida, cancelamento e execução em segundo plano.

## Validação do Android

Em 08/11/2026, os 14 testes, lintDebug e builds debug/release passaram. O APK assinado mede 1.556.152 bytes e teve a assinatura verificada. A instalação e a abertura do app e do destino de compartilhamento foram confirmadas em um emulador dedicado. O download completo e a execução em segundo plano ainda precisam de validação em aparelho físico.

## Validação do iOS

Em 08/11/2026, com Xcode 26.2, o pacote WololoKit passou em 19 testes. O build Release para simulador compilou o app e a extensão. O teste de interface do scheme `WololoUITests` passou no simulador iPhone 17 com iOS 26.2, cobrindo abertura do app, rejeição de um link não suportado, fechamento do teclado e acesso às configurações de servidor e chave. O archive de dispositivo também passou com assinatura automática da equipe pessoal.

O RF-08 tem dois comportamentos distintos no iOS. Quando o arquivo já está disponível, a transferência usa `URLSession` em segundo plano e o sistema pode entregar a conclusão ao app principal. Enquanto o servidor ainda prepara o arquivo ou mantém o job na fila, a extensão faz polling apenas enquanto está ativa. Fechar a extensão nessa fase exige abrir Wololo para retomar o acompanhamento. Uma notificação local depende de o código receber a conclusão e da permissão de notificações concedida pelo usuário.

A extensão salva MP4 em Fotos com permissão de adicionar. Para MP3, oferece **Save to Files** pelo seletor de documentos. O app principal salva áudio em sua pasta Documents, visível em Arquivos. A fila e os arquivos temporários são compartilhados pelo App Group.

O teste automatizado de interface cobre a tela principal. O compartilhamento a partir de apps reais, a gravação final em Fotos e Arquivos, a retomada após encerramento forçado e as trocas de rede ainda precisam ser validados no iPhone com o build distribuído. As metas de tempo, taxa de sucesso, memória e tamanho instalado do PRD dependem dessa medição no aparelho.

## Referências

- [Assinatura no GitHub Actions](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)
- [Upload de builds iOS](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)
- [Provisioning Ad Hoc](https://developer.apple.com/help/account/provisioning-profiles/create-an-ad-hoc-provisioning-profile/)
- [Transferências em extensões](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/ExtensionScenarios.html)
