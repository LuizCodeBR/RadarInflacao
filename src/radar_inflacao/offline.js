"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const label = period => names[Number(period.slice(5)) - 1] + "/" + period.slice(0, 4);
  const explains = {
    monthly: "A variação mensal compara os preços de um mês com os do mês anterior.",
    year_to_date: "O acumulado no ano considera de janeiro até o mês de cada observação, mesmo quando seu filtro começa depois de janeiro.",
    twelve_month: "O acumulado em 12 meses considera o mês de cada observação e os 11 meses anteriores, mesmo quando o filtro mostra apenas um mês."
  };
  let data, selected = [], objectURL = null;
  const fields = ["ipca", "inpc", "difference"];
  const colors = {ipca: "#086e67", inpc: "#b34d16", positive: "#245ca5", negative: "#a74337"};
  const svgNS = "http://www.w3.org/2000/svg";
  const element = (tag, attrs = {}, text = null) => {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== null) node.textContent = text;
    return node;
  };
  const text = (id, value) => { byId(id).textContent = value; };
  function options(select, values) {
    select.replaceChildren(...values.map(([value, caption]) => new Option(caption, value)));
  }
  function fail(message) {
    selected = [];
    byId("results").hidden = true;
    byId("download").disabled = true;
    byId("error").hidden = false;
    text("error", message);
    text("range", "Nenhum período aplicado.");
    text("download-status", "");
  }
  function validate() {
    if (!Array.isArray(data.rows) || !data.rows.length || data.rows.length > 1200) throw Error("A amostra está incompleta. Extraia novamente o ZIP.");
    let previous = null;
    for (const row of data.rows) {
      if (!/^20\d\d-(0[1-9]|1[0-2])$/.test(row.period)) throw Error("Mês inválido na amostra.");
      const serial = Number(row.period.slice(0, 4)) * 12 + Number(row.period.slice(5));
      if (previous !== null && serial !== previous + 1) throw Error("Há uma lacuna ou duplicação na amostra.");
      previous = serial;
      for (const key of fields) for (const measure of Object.keys(explains)) {
        const value = row.values[key][measure];
        if (typeof value !== "string" || !/^-?\d+(\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) throw Error("Valor inválido na amostra.");
        if (typeof row.display[key][measure] !== "string") throw Error("Rótulo inválido na amostra.");
      }
      if (typeof row.csv !== "string" || !row.csv.startsWith(row.period + ";") || !row.csv.endsWith("\r\n")) throw Error("Exportação incompleta na amostra.");
    }
    if (data.start !== data.rows[0].period || data.end !== data.rows.at(-1).period || typeof data.csv_header !== "string") throw Error("Cobertura inválida na amostra.");
  }
  function lineText(row, measure) {
    return label(row.period) + ": IPCA " + row.display.ipca[measure] + "%; INPC " + row.display.inpc[measure] + "%; diferença " + row.display.difference[measure] + " p.p.";
  }
  function plot(containerId, difference = false) {
    const container = byId(containerId);
    const measure = byId("measure").value;
    const width = Math.max(240, Math.round(container.getBoundingClientRect().width));
    const height = difference ? 260 : 300;
    const padding = {left: 51, right: 18, top: 26, bottom: 35};
    const left = padding.left, right = width - padding.right, top = padding.top, bottom = height - padding.bottom;
    const values = selected.flatMap(row => difference ? [Number(row.values.difference[measure])] : [Number(row.values.ipca[measure]), Number(row.values.inpc[measure])]);
    let lo = Math.min(0, ...values), hi = Math.max(0, ...values);
    const span = Math.max(hi - lo, .1);
    lo -= span * .12; hi += span * .12;
    const y = value => bottom - (value - lo) / (hi - lo) * (bottom - top);
    const x = index => selected.length === 1 ? (left + right) / 2 : left + 18 + index / (selected.length - 1) * (right - left - 36);
    const svg = element("svg", {viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-labelledby": containerId + "-title " + containerId + "-description"});
    svg.append(element("title", {id: containerId + "-title"}, (difference ? "Diferenças INPC menos IPCA" : "Evolução de IPCA e INPC") + " — " + data.measures[measure]));
    svg.append(element("desc", {id: containerId + "-description"}, `${selected.length} meses, de ${label(selected[0].period)} a ${label(selected.at(-1).period)}. Os valores estão disponíveis no seletor Detalhar mês e na tabela abaixo.`));
    svg.append(element("text", {x: left, y: 12}, difference ? "pontos percentuais" : "variação (%)"));
    for (let i = 0; i <= 4; i++) {
      const value = lo + (hi - lo) * i / 4;
      svg.append(element("line", {x1: left, x2: right, y1: y(value), y2: y(value), stroke: "#e4ecee"}));
      svg.append(element("text", {x: left - 8, y: y(value) + 4, "text-anchor": "end"}, (Math.abs(value) < .005 ? 0 : value).toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2})));
    }
    svg.append(element("line", {x1: left, x2: right, y1: y(0), y2: y(0), stroke: "#8298a1", "stroke-dasharray": "4 3"}));
    const tickCount = Math.min(selected.length, width < 500 ? 3 : 6);
    for (let i = 0; i < tickCount; i++) {
      const index = tickCount === 1 ? 0 : Math.round(i * (selected.length - 1) / (tickCount - 1));
      svg.append(element("text", {x: x(index), y: height - 9, "text-anchor": tickCount === 1 ? "middle" : i === 0 ? "start" : i === tickCount - 1 ? "end" : "middle"}, label(selected[index].period)));
    }
    const focused = byId("detail-month").value;
    const focusIndex = selected.findIndex(row => row.period === focused);
    if (focusIndex >= 0 && selected.length > 1) svg.append(element("line", {x1: x(focusIndex), x2: x(focusIndex), y1: top, y2: bottom, stroke: "#b4c8c4", "stroke-dasharray": "2 4"}));
    if (difference) {
      const barWidth = Math.min(34, (right - left) / Math.max(selected.length, 1) * .68);
      selected.forEach((row, i) => {
        const value = Number(row.values.difference[measure]);
        const bar = element("rect", {x: x(i) - barWidth / 2, y: value === 0 ? y(0) - 1 : Math.min(y(0), y(value)), width: barWidth, height: Math.max(2, Math.abs(y(value) - y(0))), rx: 2, fill: value < 0 ? colors.negative : value > 0 ? colors.positive : "#8298a1", "data-value": row.values.difference[measure]});
        bar.append(element("title", {}, lineText(row, measure)));
        svg.append(bar);
      });
    } else {
      for (const key of ["ipca", "inpc"]) {
        const path = selected.map((row, i) => `${i ? "L" : "M"}${x(i)},${y(Number(row.values[key][measure]))}`).join(" ");
        svg.append(element("path", {d: path, fill: "none", stroke: colors[key], "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round", "data-series": key}));
        selected.forEach((row, i) => {
          const circle = element("circle", {cx: x(i), cy: y(Number(row.values[key][measure])), r: (row.period === focused || selected.length === 1 ? 5 : selected.length <= 24 ? 3 : 2) * (key === "inpc" && Number(row.values.ipca[measure]) === Number(row.values.inpc[measure]) ? .65 : 1), fill: colors[key], stroke: "white", "stroke-width": 1.3, "data-point": key});
          circle.append(element("title", {}, lineText(row, measure)));
          svg.append(circle);
        });
      }
    }
    // Uma área de interação ampla por mês: funciona por clique/toque sem exigir hover.
    selected.forEach((row, i) => {
      const step = selected.length === 1 ? right - left : (right - left) / (selected.length - 1);
      const area = element("rect", {x: Math.max(left - 9, x(i) - step / 2), y: top, width: Math.min(right + 9, x(i) + step / 2) - Math.max(left - 9, x(i) - step / 2), height: bottom - top, fill: "transparent", "data-month": row.period, style: "cursor:pointer"});
      area.append(element("title", {}, lineText(row, measure)));
      area.addEventListener("click", () => { byId("detail-month").value = row.period; updateDetail(); });
      svg.append(area);
    });
    container.replaceChildren(svg);
  }
  function updateDetail() {
    if (!selected.length) return;
    const measure = byId("measure").value;
    const row = selected.find(item => item.period === byId("detail-month").value);
    byId("detail-values").replaceChildren(...fields.map((key, i) => {
      const span = document.createElement("span");
      const strong = document.createElement("strong");
      span.append(["IPCA ", "INPC ", "Diferença "][i]);
      strong.textContent = row.display[key][measure] + (key === "difference" ? " p.p." : "%");
      span.append(strong);
      return span;
    }));
    for (const tr of byId("rows").children) tr.classList.toggle("selected", tr.dataset.period === row.period);
    plot("evolution"); plot("difference", true);
  }
  function apply() {
    const start = byId("start").value, end = byId("end").value, measure = byId("measure").value;
    if (start > end) { fail("O mês inicial precisa ser anterior ou igual ao mês final. Ajuste o período para ver os dados e baixar o CSV."); return; }
    const a = data.rows.findIndex(row => row.period === start), b = data.rows.findIndex(row => row.period === end);
    if (a < 0 || b < a || !Object.hasOwn(explains, measure)) { fail("Selecione um período e um indicador disponíveis na amostra."); return; }
    selected = data.rows.slice(a, b + 1);
    byId("error").hidden = true;
    byId("results").hidden = false;
    byId("download").disabled = false;
    text("range", `${label(start)} a ${label(end)} · ${selected.length} ${selected.length === 1 ? "mês" : "meses"}`);
    text("download-status", "");
    text("measure-title", data.measures[measure]);
    text("card-month", "Último mês do recorte: " + label(end));
    const last = selected.at(-1);
    for (const [key, id] of [["ipca", "ipca-value"], ["inpc", "inpc-value"], ["difference", "diff-value"]]) text(id, last.display[key][measure]);
    text("explanation", explains[measure]);
    text("evolution-subtitle", data.measures[measure] + " · valores oficiais (%)");
    text("table-caption", data.measures[measure] + " · " + label(start) + " a " + label(end));
    text("row-count", selected.length + (selected.length === 1 ? " observação por índice" : " observações por índice"));
    const previous = byId("detail-month").value;
    options(byId("detail-month"), selected.map(row => [row.period, label(row.period)]));
    byId("detail-month").value = selected.some(row => row.period === previous) ? previous : end;
    byId("rows").replaceChildren(...selected.map(row => {
      const tr = document.createElement("tr"); tr.dataset.period = row.period;
      const th = document.createElement("th"); th.scope = "row"; th.textContent = label(row.period); tr.append(th);
      fields.forEach(key => { const td = document.createElement("td"); td.textContent = row.display[key][measure]; tr.append(td); });
      return tr;
    }));
    updateDetail();
  }
  function download() {
    if (!selected.length || byId("download").disabled) return;
    if (objectURL) URL.revokeObjectURL(objectURL);
    const contents = "\uFEFF" + data.csv_header + selected.map(row => row.csv).join("");
    objectURL = URL.createObjectURL(new Blob([contents], {type: "text/csv;charset=utf-8"}));
    const anchor = document.createElement("a");
    anchor.href = objectURL;
    anchor.download = `radar-ipca-inpc-${selected[0].period}-a-${selected.at(-1).period}.csv`;
    document.body.append(anchor); anchor.click(); anchor.remove();
    text("download-status", "CSV preparado com " + selected.length + " meses e os três indicadores. Para guardar no D:, escolha essa unidade ao salvar.");
  }
  try {
    data = JSON.parse(byId("radar-data").textContent);
    validate();
    const months = data.rows.map(row => [row.period, label(row.period)]);
    options(byId("start"), months); options(byId("end"), months);
    options(byId("measure"), Object.entries(data.measures));
    text("coverage", label(data.start) + " — " + label(data.end));
    text("sample-count", data.rows.length + " meses · 2 índices · 3 indicadores");
    text("version", "Radar da Inflação " + data.version + " · Demonstração offline");
    data.sources.forEach(source => {
      const section = document.createElement("div"); section.className = "source";
      const name = document.createElement("strong"); name.textContent = source.index + " · IBGE / SIDRA " + (source.index === "IPCA" ? "1737" : "1736"); section.append(name);
      const date = document.createElement("p"); date.textContent = "Coleta original: " + source.retrieved_at + " · Amostra incluída"; section.append(date);
      const hash = document.createElement("p"); hash.append("SHA-256: "); const code = document.createElement("code"); code.textContent = source.sha256; hash.append(code); section.append(hash);
      const link = document.createElement("a"); link.href = source.url; link.textContent = "Consultar a fonte no IBGE (requer internet) ↗"; link.target = "_blank"; link.rel = "noopener noreferrer"; section.append(link);
      byId("sources").append(section);
    });
    byId("end").value = data.end;
    byId("start").value = data.rows[Math.max(0, data.rows.length - 12)].period;
    for (const id of ["start", "end", "measure"]) byId(id).addEventListener("change", apply);
    byId("detail-month").addEventListener("change", updateDetail);
    byId("download").addEventListener("click", download);
    byId("all").addEventListener("click", () => { byId("start").value = data.start; byId("end").value = data.end; apply(); });
    byId("last-year").addEventListener("click", () => { byId("start").value = data.rows[Math.max(0, data.rows.length - 12)].period; byId("end").value = data.end; apply(); });
    let frame = null;
    const observer = new ResizeObserver(() => { if (frame) cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { if (selected.length) { plot("evolution"); plot("difference", true); } }); });
    observer.observe(byId("evolution"));
    window.addEventListener("pagehide", () => { if (objectURL) URL.revokeObjectURL(objectURL); });
    apply();
  } catch (error) {
    fail("Não foi possível abrir a demonstração. Extraia novamente o pacote. " + error.message);
  }
})();
