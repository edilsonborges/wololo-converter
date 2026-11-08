# PRD — Wololo Mobile (iOS e Android nativos)

As of 2026-11-08 · versão viva (editável e com comentários): https://claude.ai/artifact/Uit6ygFg7FR8phr7Vy2Wm8
Se as duas versões divergirem, vale a do link acima.

## Visão geral

O Wololo Mobile são dois apps nativos, um em Swift (iOS) e outro em Kotlin (Android), para salvar vídeo ou áudio direto da folha de compartilhar, em dois toques. Todo o trabalho pesado continua no servidor Wololo (yt-dlp, ffmpeg); o app só envia o link, acompanha o progresso e salva o arquivo.

**Problema.** Hoje, para baixar um vídeo do X no celular, a pessoa copia o link, abre o navegador, cola no site e depois move o arquivo de Downloads para a galeria. São mais de 6 passos e duas trocas de app.

**Objetivo.** Compartilhar → Wololo → o vídeo aparece na galeria, sem abrir navegador nem o app.

**Métricas de sucesso**

- Do toque em "Wololo" até o arquivo na galeria: até 15 s para um vídeo de 1 min em 720p (rede Wi-Fi).
- Taxa de sucesso do download: ≥ 95% para links válidos das plataformas suportadas.
- Tamanho instalado: ≤ 5 MB no iOS e ≤ 4 MB de APK no Android.
- Nenhum crash na extensão de compartilhar em 1 semana de uso pelo grupo de testes.

## Usuários e cenários

O público é o dono do servidor e um círculo de amigos (até ~100 pessoas), não o público geral da loja.

| Cenário | Onde começa | O que espera |
| --- | --- | --- |
| Salvar um vídeo engraçado do X para mandar no WhatsApp | Botão compartilhar do app do X | Vídeo na galeria em segundos |
| Guardar um Reels ou TikTok | Compartilhar do Instagram ou TikTok | Vídeo na galeria, sem marca d'água extra |
| Pegar só a música de um vídeo do YouTube | Compartilhar do app do YouTube | MP3 no app Arquivos (iOS) ou em Músicas (Android) |
| Baixar as faixas de um álbum de música | Link de página de música colado no app | Um MP3 por faixa encontrada, aviso das que faltarem |
| Ver o que já baixou | Abrindo o app | Histórico com status e botão de baixar de novo |

## Escopo do MVP

O MVP entrega a extensão de compartilhar e uma tela de histórico; todo o resto fica para depois.

**Dentro**

- Receber um link pela folha de compartilhar (iOS Share Extension, Android share target).
- Escolher MP4 (qualidade padrão 720p, ajustável) ou MP3 com um toque.
- Mostrar progresso e salvar automaticamente: vídeo na galeria, MP3 em Arquivos (iOS) ou Music/Wololo (Android).
- Notificação quando terminar ou falhar, com o motivo.
- Tela principal: colar link, fila e histórico local dos últimos 50 downloads.
- Links de página de música resolvidos em várias faixas, como no site (sem aparecer na lista de plataformas).
- Configurações: endereço do servidor, qualidade padrão, formato padrão.

**Fora (por enquanto)**

- Baixar sem servidor (yt-dlp no aparelho).
- Conta de usuário, login ou sincronização de histórico entre aparelhos.
- Playlists inteiras e canais.
- iPad, Apple Watch, widgets e tablets Android com layout próprio.
- Publicação na App Store e no Google Play (ver Distribuição).

## Fluxos

```
Celular:   Compartilha (X/Insta/TikTok) → Extensão Wololo (MP4 ou MP3) ─┬─ link de vídeo ──→ POST /api/download (job na fila)
                                                                        └─ link de música ─→ POST /api/resolve → um job por faixa
Servidor:  yt-dlp + ffmpeg geram MP4/MP3 ──(polling GET /api/jobs/{id} a cada 1 s até "completed")──→
Celular:   Baixa o arquivo em segundo plano → Salva na galeria/Arquivos → Notifica
```

Pela tela principal o fluxo é o mesmo, começando por colar o link.

## Requisitos funcionais

Os requisitos valem para as duas plataformas; diferenças de implementação estão nas seções de iOS e Android.

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-01 | Aparecer na folha de compartilhar para links (URL ou texto com URL) | Must |
| RF-02 | Extrair a primeira URL válida do texto recebido (X e Instagram mandam texto + link) | Must |
| RF-03 | Validar a plataforma localmente com as mesmas regras do site antes de chamar o servidor | Must |
| RF-04 | Escolha MP4 / MP3 na extensão; lembrar a última escolha | Must |
| RF-05 | Iniciar o job em `POST /api/download` e acompanhar por polling de `GET /api/jobs/{id}` a cada 1 s | Must |
| RF-06 | Baixar o arquivo de `GET /api/jobs/{id}/download` em streaming para disco, nunca em memória | Must |
| RF-07 | Salvar vídeo na galeria e MP3 em Arquivos / Music, com o nome do título | Must |
| RF-08 | Continuar em segundo plano se a pessoa fechar a extensão; avisar por notificação | Must |
| RF-09 | Cancelar um download em andamento (`DELETE /api/jobs/{id}`) | Should |
| RF-10 | Resolver links de página de música via `POST /api/resolve` e enfileirar uma faixa MP3 por resultado | Should |
| RF-11 | Histórico local (últimos 50): título, plataforma, formato, duração do download, status, tentar de novo | Should |
| RF-12 | Mensagens de erro claras: privado, indisponível, servidor fora do ar, limite de downloads (HTTP 429) | Must |
| RF-13 | Configurar endereço do servidor (padrão `https://wololo.edilson.dev`) e chave de acesso | Must |
| RF-14 | Abrir um link compartilhado pelo atalho `wololo.edilson.dev/<link>` direto no app (deep link) | Could |

## iOS (Swift)

O app iOS é SwiftUI puro, sem dependências externas, com dois alvos que compartilham um pacote local `WololoKit`.

| Item | Decisão |
| --- | --- |
| Versão mínima | iOS 17 (SwiftUI + Observation) |
| Alvos | App principal + Share Extension; App Group `group.dev.edilson.wololo` para dividir configurações, fila e arquivos |
| `WololoKit` (Swift Package local) | Cliente da API (`URLSession` + `async/await`, `Codable`), detecção de plataforma, modelos, histórico em JSON no App Group |
| Dependências de terceiros | Nenhuma |
| Salvar vídeo | `PHPhotoLibrary` com permissão só de adicionar (`NSPhotoLibraryAddUsageDescription`) + `PHAssetCreationRequest` a partir do arquivo em disco |
| Salvar MP3 | Pasta Documents do app com `UIFileSharingEnabled` e `LSSupportsOpeningDocumentsInPlace`: aparece em Arquivos › No meu iPhone › Wololo |
| Notificações | `UserNotifications` local ao terminar ou falhar |
| Chave de acesso | Keychain compartilhado pelo App Group |

**Como a extensão lida com os limites do iOS**

- A Share Extension tem pouca memória (cerca de 120 MB) e pode ser encerrada quando a pessoa a fecha. Por isso ela nunca carrega o vídeo em memória.
- Enquanto o servidor processa, a extensão mostra o progresso (polling do job). Em vídeos curtos tudo termina com ela aberta.
- Quando o job fica pronto, o arquivo é baixado por uma `URLSession` em segundo plano com `sharedContainerIdentifier`. Se a extensão for fechada, o sistema conclui o download e acorda o app principal (`handleEventsForBackgroundURLSession`), que salva na galeria e notifica.
- Se a pessoa fechar a extensão antes do job ficar pronto, o `job_id` fica na fila do App Group e o app principal retoma ao ser aberto ou por notificação.

## Android (Kotlin)

O app Android é um módulo só, em Kotlin com Jetpack Compose, e o download roda no WorkManager para sobreviver ao fechamento da tela.

| Item | Decisão |
| --- | --- |
| Versões | `minSdk` 26 (Android 8), `targetSdk` 35 |
| UI | Jetpack Compose + Material 3, sem a biblioteca de ícones estendida; R8 com minificação e remoção de recursos |
| Receber links | `ShareActivity` translúcida (bottom sheet) com `intent-filter` `ACTION_SEND` / `text/plain` |
| Rede | OkHttp + kotlinx.serialization (únicas dependências além do AndroidX) |
| Trabalho em segundo plano | `CoroutineWorker` do WorkManager como trabalho em primeiro plano (`ForegroundInfo`, tipo `dataSync`), com progresso na notificação |
| Salvar vídeo | `MediaStore.Video` em `Movies/Wololo` (sem permissão de armazenamento a partir do Android 10; `WRITE_EXTERNAL_STORAGE` só até o 9) |
| Salvar MP3 | `MediaStore.Audio` em `Music/Wololo` |
| Notificações | Canal "Downloads"; pede `POST_NOTIFICATIONS` no Android 13+ |
| Configurações e histórico | DataStore; chave de acesso cifrada com o Android Keystore |

**Fluxo no Android**

1. A `ShareActivity` abre por cima do app de origem, extrai a URL e mostra MP4 / MP3.
2. Ao tocar, enfileira um `DownloadWorker` com a URL e o formato e fecha em menos de 1 s.
3. O worker inicia o job, faz polling, baixa o arquivo em streaming direto para o `MediaStore` e atualiza a notificação.
4. A notificação final abre o vídeo na galeria ou o MP3 no player padrão.

## Backend

Os apps usam a API que o site já usa (v0.8.1); são necessárias três mudanças pequenas no servidor antes do lançamento.

**Endpoints usados (já existem)**

| Endpoint | Uso no app |
| --- | --- |
| `POST /api/download` `{url, quality}` | Inicia o job; `quality` = `360p`…`1080p` ou `mp3` |
| `GET /api/jobs/{id}` | Polling de status, progresso, velocidade, título e erro |
| `GET /api/jobs/{id}/download` | Arquivo final, com `Content-Disposition` e `Content-Length` |
| `DELETE /api/jobs/{id}` | Cancelar |
| `POST /api/resolve` `{url}` | Links de página de música → lista de faixas com `video_url` |
| `GET /api/health` | Teste de conexão na tela de configurações |

O SSE (`/api/jobs/{id}/progress`) fica de fora: polling de 1 s é mais simples nos dois sistemas e sobrevive melhor a troca de rede.

**Mudanças necessárias**

1. **Chave de acesso.** Header `X-Wololo-Key` com chaves configuradas no `.env`. O limite de 10 downloads/min passa a contar por chave, porque vários celulares na rede da operadora saem pelo mesmo IP. O site continua funcionando sem chave.
2. **Fila no servidor em vez de HTTP 429.** Hoje o servidor recusa quando já há 3 downloads simultâneos; os apps precisariam ficar tentando de novo. O job deve entrar como `queued` e começar quando abrir vaga.
3. **Versão mínima do app.** `GET /api/health` passa a devolver `min_app_version`, para avisar quem estiver com um build antigo depois de uma mudança incompatível.

## Requisitos não funcionais

Leveza é o requisito que decide empates: nada de framework multiplataforma, SDK de análise ou biblioteca de UI.

| Área | Requisito |
| --- | --- |
| Tamanho | iOS ≤ 5 MB instalado; Android ≤ 4 MB de APK (release, R8) |
| Partida | Folha de compartilhar visível em ≤ 500 ms após tocar em Wololo |
| Memória | Extensão iOS ≤ 60 MB de pico; arquivos sempre em streaming para disco |
| Bateria e rede | Polling só enquanto há job ativo; para ao concluir, falhar ou após 15 min |
| Privacidade | Sem analítica nem rastreamento; nenhum dado sai do aparelho além do link para o servidor Wololo; histórico só local |
| Segurança | HTTPS obrigatório (ATS no iOS, `cleartextTrafficPermitted=false` no Android); chave guardada no Keychain / Keystore |
| Acessibilidade | Dynamic Type / tamanho de fonte do sistema, VoiceOver e TalkBack nos controles da folha de compartilhar |
| Idioma | Interface em inglês, como o site; textos em arquivos de tradução para incluir português depois |
| Testes | Testes unitários do cliente da API e da detecção de plataforma com os mesmos casos do site |

## Distribuição e riscos

Os dois apps devem ser distribuídos fora das lojas públicas: as regras da Apple e do Google barram apps que baixam mídia do YouTube e de outras redes sem autorização delas. As regras abaixo são de memória e precisam ser conferidas no texto atual antes de decidir.

**Caminhos de distribuição**

| Plataforma | Caminho | Limite | Revisão da loja |
| --- | --- | --- | --- |
| iOS | TestFlight interno | 100 pessoas, adicionadas como usuários da conta no App Store Connect; build expira em 90 dias | Não |
| iOS | Ad Hoc (link de instalação) | 100 iPhones por ano de assinatura, cadastrados pelo UDID | Não |
| iOS | TestFlight externo / App Store | Até 10.000 testadores / público | Sim; provável recusa pela diretriz 5.2.3 (baixar mídia de terceiros) |
| Android | APK assinado baixado do site Wololo | Sem limite | Não; requer cadastro como desenvolvedor verificado do Google para instalação em celulares certificados no Brasil (regra prevista para 2026) |
| Android | Google Play | Público | Sim; provável remoção por baixar conteúdo do YouTube |

Recomendação: TestFlight interno para você, Ad Hoc para os amigos no iOS e APK pelo site no Android.

**Riscos**

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Plataforma muda e o download quebra | Alto | A lógica fica no servidor: atualizar o yt-dlp resolve sem novo build do app |
| Muita gente ao mesmo tempo satura o servidor (3 downloads simultâneos) | Médio | Fila no servidor, chave por pessoa, limite por chave |
| Limite de 100 iPhones do Ad Hoc acaba | Baixo | Remover aparelhos na renovação anual; priorizar TestFlight interno |
| Uso para pirataria ou violação de termos das plataformas | Médio | App só para o círculo de amigos, sem divulgação pública; aviso de uso pessoal na primeira abertura |
| Mudança incompatível na API quebra builds antigos | Baixo | `min_app_version` no health e aviso de atualização |

## Plano de entrega

A entrega vai em cinco marcos em sequência, cada um com um critério de pronto; as datas ficam para depois das decisões em aberto.

1. **Backend pronto para apps.** Chave de acesso, fila no servidor e `min_app_version` publicados numa versão nova. Pronto quando um `curl` com chave entra na fila em vez de receber 429.
2. **iOS: extensão de compartilhar.** `WololoKit` + Share Extension salvando MP4 na galeria e MP3 em Arquivos. Pronto quando um vídeo do X vai para a galeria sem abrir o app principal.
3. **Android: share target.** `ShareActivity` + `DownloadWorker` salvando no MediaStore. Pronto quando o mesmo vídeo do X chega na galeria com o app fechado.
4. **Telas principais nos dois.** Colar link, fila, histórico, configurações e links de página de música. Pronto quando os requisitos Must e Should passam nos dois aparelhos.
5. **Distribuição para o grupo.** TestFlight interno + Ad Hoc no iOS e APK no site. Pronto com 5 amigos usando por uma semana sem crash na extensão.

## Perguntas em aberto

- [ ] Qualidade padrão do MP4 no app: 720p (proposta) ou 480p como o download direto do site?
- [ ] A extensão pergunta MP4/MP3 toda vez, ou salva direto no formato padrão com um toque só?
- [ ] Amigos no iOS: Ad Hoc (coletar UDID de cada iPhone) ou TestFlight interno (adicionar cada um na conta do App Store Connect)?
- [ ] Uma chave de acesso por pessoa (dá para revogar individualmente) ou uma chave única para o grupo?
- [ ] Identificador dos apps: `dev.edilson.wololo` serve?
- [ ] O histórico do app deve mostrar também os downloads feitos pelo site (exigiria login), ou só os do aparelho?
- [ ] Quantos downloads simultâneos o servidor deve aceitar depois da fila (hoje 3)?
