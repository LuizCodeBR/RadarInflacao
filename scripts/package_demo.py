"""Prepara ZIP de demonstração: só HTML + instruções, sem Python no destino."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from radar_inflacao import __version__
from radar_inflacao.offline import load_sample_indices, make_payload, render_html


def package_demo(output_directory):
    root = Path(__file__).resolve().parents[1]
    indices = load_sample_indices(root / "sample")
    payload = make_payload(indices)
    html = render_html(indices).encode("utf-8")
    instructions = (
        f"RADAR DA INFLAÇÃO — DEMONSTRAÇÃO OFFLINE {__version__}\n\n"
        "1. Extraia este ZIP em uma pasta gravável. No seu computador, pode ser no D:.\n"
        "2. Abra ABRIR-DEMONSTRACAO.html com Edge, Chrome ou Firefox atualizado.\n"
        "3. Escolha os meses e o indicador. Clique em Baixar CSV do período para exportar.\n\n"
        "Não exige Python, terminal, instalação, conta ou internet depois de baixar.\n"
        "Mantenha JavaScript habilitado no navegador. Não abra o HTML dentro do ZIP.\n"
        "O arquivo é portátil: pode estar em outra pasta ou unidade, sem editar caminhos.\n\n"
        f"Amostra incluída: {payload['start']} a {payload['end']}, "
        f"{len(payload['rows'])} meses. Não há atualização automática.\n"
        "As datas originais e fontes aparecem em Entenda o que está comparando.\n"
        "O mês inicial e o final são incluídos. A medida escolhida afeta gráfico e tabela.\n"
        "O CSV contém os três indicadores, diferenças INPC menos IPCA e a procedência.\n"
        "O CSV usa UTF-8 com BOM, ponto e vírgula e vírgula decimal.\n"
        "Se precisar, importe como CSV no Excel/LibreOffice com essas opções.\n"
        "A coluna Coleta ID identifica a amostra de modo reprodutível, não uma coleta nova.\n\n"
        "EXPERIMENTE\n"
        "Escolha outubro/2026 nos dois meses e Variação mensal:\n"
        "IPCA 0,14%; INPC 0,22%; diferença +0,08 ponto percentual.\n"
        "Troque para Acumulado em 12 meses: 4,63%; 4,49%; diferença -0,14 p.p.\n"
        "Use Detalhar mês, o teclado ou clique no gráfico para explorar outra observação.\n"
        "Para salvar o CSV no D:, escolha a unidade na janela de download do navegador.\n\n"
        "O aplicativo completo permite consultar novos dados do IBGE, manter um banco\n"
        "e analisar grupos e áreas. A demonstração inclui somente IPCA × INPC.\n"
        "Projeto: https://github.com/LuizCodeBR/RadarInflacao\n"
        "Abrir esse link exige internet; explorar a demonstração não.\n"
    ).encode()
    name = f"RadarInflacao-Demo-{__version__}"
    members = {"ABRIR-DEMONSTRACAO.html": html, "LEIA-ME.txt": instructions}
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for filename, content in members.items():
            info = ZipInfo(f"{name}/{filename}", date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    raw = stream.getvalue()
    # Tudo é validado e montado em memória antes de criar a pasta de entrega.
    output_directory.mkdir(parents=True, exist_ok=False)
    for filename, content in members.items():
        (output_directory / filename).write_bytes(content)
    target = output_directory / f"{name}.zip"
    target.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (output_directory / "SHA256SUMS.txt").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    result = {
        "version": __version__,
        "zip": str(target),
        "bytes": len(raw),
        "sha256": digest,
        "html_bytes": len(html),
        "months": len(payload["rows"]),
    }
    (output_directory / "entrega.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package_demo(args.output_dir), ensure_ascii=False))
