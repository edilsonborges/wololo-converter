# Prompt inicial — agente do Wololo Mobile

Cole o texto abaixo para iniciar o agente na raiz do repositório `wololo-converter`.

---

Você vai construir os apps nativos do Wololo Converter: **iOS em Swift/SwiftUI** e **Android em Kotlin**, leves,
que aparecem na folha de compartilhar e salvam o vídeo (MP4) ou o áudio (MP3) na galeria usando o servidor Wololo
que já existe neste repositório.

Antes de qualquer coisa, leia nesta ordem:
1. `ai-docs/HANDOFF.md` — estado do repo, restrições, ambiente, contrato da API, processo de release.
2. `ai-docs/mobile-prd.md` — o PRD (requisitos RF-01…RF-14, decisões de iOS/Android, marcos).
3. `CLAUDE.md` — comandos e arquitetura do projeto.

Regras importantes (detalhes no handoff):
- Não toque nos containers de produção (portas 47651/47652); teste com instâncias isoladas (ex.: 57652).
- O recurso de links de página de música (`/api/resolve`) é discreto: sem ícone, sem lista de plataformas, e sem
  mencioná-lo em CHANGELOG, notas de release ou mensagens de commit.
- Não faça push, release ou deploy sem eu pedir. Fale comigo em português; a interface dos apps é em inglês.
- Este Mac está no macOS 12.7 sem Xcode, sem JDK e sem Android SDK. Não assuma que dá para buildar localmente.

Comece pelo **Marco 1 (backend pronto para apps)** do PRD:
- chave de acesso via header `X-Wololo-Key` com rate limit por chave;
- fila no servidor em vez de HTTP 429 quando há 3 downloads ativos;
- `min_app_version` em `GET /api/health`.
Implemente com testes (backend roda em `python:3.12-slim` via Docker, comando no handoff) e me mostre o
resultado antes de fazer a release.

Em paralelo, me traga **uma recomendação objetiva de onde buildar o iOS** (outro Mac com macOS 14+ vs. CI no
GitHub Actions com assinatura por App Store Connect API key) e do que você precisa de mim para cada opção
(certificados, chaves, IDs). Depois disso, proponha a estrutura de `mobile/ios` e `mobile/android` antes de
gerar os projetos.
