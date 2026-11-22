# Na TV Agora

Agenda esportiva da TV brasileira no horário de Lisboa: o que está ao vivo (com placar), os melhores jogos do dia e onde passa cada um.

- **Página:** `index.html`, servida pelo GitHub Pages. No iPhone: abrir no Safari → Compartilhar → Adicionar à Tela de Início.
- **Agenda:** `data/agenda.json`, gerada por `scripts/gerar_agenda.py` a cada 3 horas (`.github/workflows/agenda.yml`).

## Como a agenda é montada

1. Jogos do dia na ESPN (futebol, NBA, NFL, NHL).
2. Nota de 1 a 3 estrelas: peso da competição, times grandes, fase decisiva, seleção brasileira.
3. Canal confirmado pela programação do meuguia.tv (ESPN, SporTV, Premiere, BandSports, Globo, Record...).
   Sem canal no guia, usa a tabela `DIREITOS` (canal provável). Sem canal nenhum, o jogo fica de fora.
4. Extras: tudo que o guia marca "Ao Vivo" em esporte e não veio da ESPN (F1, MotoGP, tênis, futsal, vôlei, lutas...).

Para ajustar pesos, times grandes ou direitos de transmissão, edite as tabelas no começo do script.

Rodar à mão: `python3 scripts/gerar_agenda.py`
