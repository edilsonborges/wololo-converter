# Handoff — Wololo Mobile (iOS + Android nativos)

Data: 2026-11-08 · Estado do repo no handoff: `main` em v0.8.1 (`8eb38f3`)
Dono: Edilson (fala português; interface do produto é em inglês)

## 1. Objetivo do trabalho

Construir dois apps nativos e leves, **Swift/SwiftUI (iOS)** e **Kotlin (Android)**, que aparecem na folha de
compartilhar e salvam o vídeo (MP4) ou o áudio (MP3) direto na galeria / arquivos, usando o servidor Wololo
existente. A especificação completa está em [`mobile-prd.md`](mobile-prd.md) (versão viva:
https://claude.ai/artifact/Uit6ygFg7FR8phr7Vy2Wm8 — se divergirem, vale o link).

Ordem de entrega (marcos do PRD): **1. backend pronto para apps** → 2. iOS share extension → 3. Android share
target → 4. telas principais → 5. distribuição para o grupo.

## 2. Restrições que NÃO são negociáveis

- **Links de página de música** (`backend/app/music_links.py`, `POST /api/resolve`): o recurso é discreto. Não
  colocar ícone nem incluí-lo na lista de plataformas suportadas, e **não mencioná-lo em CHANGELOG, notas de
  release ou mensagens de commit**. Quando uma release só tiver isso, o CHANGELOG diz apenas `- Bug fixes.` e o
  commit é genérico (ex.: `fix: release vX.Y.Z`).
- **Nunca mexer nos containers de produção** (`wololo-backend`, `wololo-frontend`, portas 47651/47652) durante
  testes. Use instâncias isoladas (ver §5). Deploy só com OK explícito do dono.
- Interface dos apps em **inglês**, como o site.
- Commits terminam com a linha de atribuição que o seu ambiente indicar; não faça push/release sem o dono pedir.

## 3. Ambiente local (descoberto no handoff)

| Item | Estado | Consequência |
| --- | --- | --- |
| macOS | 12.7.6 (Monterey), Intel | O Xcode mais novo que roda aqui é o 14.2 (SDK iOS 16). Não serve para iOS 17 nem para enviar ao TestFlight hoje |
| Xcode | **não instalado** (só Command Line Tools) | Build/assinatura de iOS precisa de outro Mac (macOS 14+) **ou CI** (GitHub Actions `macos-15`, Xcode Cloud) |
| JDK / Android SDK / Gradle | **não instalados** | Instalar JDK 17 + Android command-line tools, ou buildar o Android no GitHub Actions (`ubuntu-24.04`) |
| Python local | 3.14 — **não instala** as dependências pinadas do backend (pydantic-core) | Testes do backend rodam em container `python:3.12-slim` (comando em §5) |
| Node | 24 (frontend usa Vite/Vitest/Playwright 1.57) | OK |
| Docker | OK | Usado para testes e instâncias isoladas |
| Conta Apple Developer | o dono **tem** conta paga | Necessário para TestFlight / Ad Hoc |

**Primeira decisão a levar ao dono:** onde buildar iOS (outro Mac vs. CI no GitHub Actions com assinatura via
App Store Connect API key). Recomendação: CI, com `xcodebuild` + `altool`/`notarytool`-equivalente para TestFlight.

## 4. Mapa do repositório

```
backend/            FastAPI + yt-dlp + ffmpeg (+ Playwright/Chromium para links de música)
  app/routes.py     todas as rotas /api
  app/download_service.py   jobs em ThreadPoolExecutor, cancelamento, timeout, persistência
  app/music_links.py        resolve página de música → vídeos do YouTube
frontend/           React + Vite + Tailwind (src/hooks/useQueueManager.ts = lógica da fila)
scripts/            release.sh, update.sh (deploy por tag), check-version.sh, tracks-to-mp3.mjs
ai-docs/            este handoff, PRD, prompt inicial
CHANGELOG.md        fonte única das release notes (aparecem no modal do site)
```

Sugestão para o código novo: `mobile/ios/` (projeto Xcode + pacote local `WololoKit`) e `mobile/android/`
(projeto Gradle). O CI atual (`.github/workflows/ci.yml`) não conhece essas pastas; adicione jobs próprios.

## 5. Como rodar e testar

```bash
# Backend: testes (Python 3.12 em container, porque o 3.14 local não instala as deps)
cd backend && docker run --rm -v "$PWD":/src:ro -v wololo-pip-cache:/root/.cache/pip python:3.12-slim \
  sh -c "cp -r /src /app && cd /app && pip install -q -r requirements.txt -r requirements-test.txt && pytest -q -p no:cacheprovider"

# Backend isolado para testes reais (NÃO use 47652, é produção)
docker build -t wololo-backend:e2e backend && docker run -d --name wololo-e2e-backend -p 57652:47652 wololo-backend:e2e

# Frontend
cd frontend && npm ci && npm run test && npm run build
# E2E contra o backend isolado: crie um vite config temporário com server.port 57651 e proxy /api → 57652
```

Hoje: backend 146 testes, frontend 60 unitários + 15 Playwright (CI verde).

## 6. Contrato da API usado pelos apps (já existe)

Base: `https://wololo.edilson.dev` (produção) — rotas sob `/api`.

```http
POST /api/download        {"url": "<link>", "quality": "360p|480p|720p|1080p|mp3"}
  200 → {"job_id": "uuid", "message": "Download started", "status": "queued"}
  400 → {"detail": "<motivo>"} (URL inválida/plataforma não suportada)
  429 → limite: 3 downloads simultâneos no servidor ou 10/min por IP

GET /api/jobs/{id}
  200 → {"id","url","platform","output_format","quality","status","progress"(0-100),"speed","eta",
         "current_stage","title","filename","file_size","duration","thumbnail_url","error_message",
         "created_at","started_at","completed_at"}
  status ∈ queued | validating | downloading | converting | finalizing | completed | failed | cancelled

GET /api/jobs/{id}/download   → arquivo (Content-Disposition com filename UTF-8, Content-Length)
DELETE /api/jobs/{id}         → {"message": "Job cancelled", "job_id": "..."}
POST /api/resolve {"url"}     → {"album", "tracks":[{"title","artist","duration","source_url","video_url"|null,"video_title"}]}
                                (2–6 s por página; 10/min; 502 = página bloqueou/erro, 504 = timeout)
GET /api/health               → {"status","version","yt_dlp_version","active_downloads","temp_dir_size_mb"}
```

Detalhes de comportamento que importam para os apps:

- Arquivos expiram: a limpeza apaga pastas de jobs com mais de `MAX_FILE_AGE_HOURS` (1 h) — baixe logo.
- `DOWNLOAD_TIMEOUT_SECONDS` (1 h) mata jobs travados → `failed` com mensagem de timeout.
- Cancelamento para o yt-dlp de fato e apaga os arquivos; o job continua contando na vaga até a thread sair.
- Links aceitos: mesmas regras de `backend/app/utils.py` (`PLATFORM_PATTERNS`) e `frontend/src/urlParser.ts`.
  Replique-as nos apps (RF-03) usando os casos de teste de `frontend/src/__tests__/urlParser.test.ts`.
- `POST /api/download` aceita só vídeo; links de música passam antes por `/api/resolve` (cada `video_url` vira
  um download `mp3`).

## 7. Marco 1 — mudanças de backend (fazer primeiro)

1. **Chave de acesso**: header `X-Wololo-Key`, chaves no `.env` (ex.: `API_KEYS=nome1:chave1,nome2:chave2`).
   Rate limit por chave quando presente, por IP quando ausente. O site continua sem chave.
2. **Fila no servidor**: em vez de 429 quando há 3 jobs ativos, aceitar e deixar `queued` até abrir vaga
   (o `ThreadPoolExecutor` já enfileira; o bloqueio está em `routes.start_download`). Manter um teto de fila.
3. **`min_app_version`** em `GET /api/health` (configurável no `.env`).

Cada mudança com testes. Depois, release seguindo §8.

## 8. Processo de release (como foi feito até a v0.8.1)

1. Atualizar a versão em `VERSION`, `backend/app/version.py`, `frontend/package.json` e lock
   (`npm version X.Y.Z --no-git-tag-version`) + entrada `## [X.Y.Z] - AAAA-MM-DD` no `CHANGELOG.md`.
2. `./scripts/check-version.sh` precisa passar.
3. Commit único, tag anotada `vX.Y.Z`, `git push origin HEAD:main vX.Y.Z`. O workflow `Release` cria a GitHub
   Release; o `CI` roda os testes.
4. Deploy (só com OK do dono): `cd /Users/edilson/projects/wololo-converter && ./scripts/update.sh`
   (faz checkout da tag mais nova, rebuilda e checa o health).

## 9. Decisões pendentes (do PRD) e o padrão a usar enquanto o dono não responde

| Pergunta | Padrão provisório |
| --- | --- |
| Qualidade padrão do MP4 | 720p |
| Extensão pergunta MP4/MP3 sempre? | Sim, lembrando a última escolha |
| Amigos no iOS: Ad Hoc ou TestFlight interno | Não bloqueia o código; perguntar antes do marco 5 |
| Chave por pessoa ou única | Por pessoa (formato `nome:chave`) |
| Bundle/application id | `dev.edilson.wololo` (confirmar) |
| Histórico inclui downloads do site? | Não, só local |
| Downloads simultâneos no servidor | Manter 3, fila de até 20 |

## 10. Armadilhas já conhecidas

- O Chromium do backend roda **sem executar o JS** das páginas de música (só documento + desafio do Cloudflare);
  rodar o JS completo num container sem GPU trava a CPU.
- A busca do YouTube varia entre chamadas; o resolvedor repete a busca uma vez antes de desistir.
- `GET /api/jobs/{id}` mistura o registro do banco com o progresso ao vivo; durante o download use esse
  endpoint, não `/api/jobs` (lista).
- O `docker-compose.yml` builda o frontend a partir da raiz do repo (por causa do CHANGELOG); há um
  `.dockerignore` na raiz para isso.
