// llrp_tools -- minimal .xlsx writer (OOXML in a store-only ZIP) and the `workbook` command
#ifndef LLRP_TOOLS_XLSX_HPP
#define LLRP_TOOLS_XLSX_HPP
#include "cmd_core.hpp"

namespace xl {

static uint32_t g_crc_tab[256];
static void crc_init() {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        g_crc_tab[i] = c;
    }
}
static uint32_t crc_update(uint32_t crc, const char *p, size_t n) {
    crc = ~crc;
    for (size_t i = 0; i < n; i++) crc = g_crc_tab[(crc ^ (unsigned char)p[i]) & 0xFF] ^ (crc >> 8);
    return ~crc;
}
static void put16(string &s, unsigned v) { s += (char)(v & 0xFF); s += (char)((v >> 8) & 0xFF); }
static void put32(string &s, uint32_t v) { for (int i = 0; i < 4; i++) s += (char)((v >> (8 * i)) & 0xFF); }

struct Zip {
    FILE *f;
    struct Ent { string name; uint32_t crc, size, off; };
    vector<Ent> ents;
    explicit Zip(const string &path) : f(fopen(path.c_str(), "wb")) { if (!f) die("cannot write " + path); }
    void header(const string &name, uint32_t crc, uint32_t size) {
        string h;
        put32(h, 0x04034b50); put16(h, 20); put16(h, 0); put16(h, 0); put16(h, 0); put16(h, 0x21);
        put32(h, crc); put32(h, size); put32(h, size); put16(h, (unsigned)name.size()); put16(h, 0);
        Ent e = {name, crc, size, (uint32_t)ftell(f)};
        ents.push_back(e);
        fwrite(h.data(), 1, h.size(), f);
        fwrite(name.data(), 1, name.size(), f);
    }
    void add_blob(const string &name, const string &data) {
        header(name, crc_update(0, data.data(), data.size()), (uint32_t)data.size());
        fwrite(data.data(), 1, data.size(), f);
    }
    void add_file(const string &name, const string &path, uint32_t crc, uint32_t size) {
        header(name, crc, size);
        FILE *in = fopen(path.c_str(), "rb");
        if (!in) die("cannot read " + path);
        char buf[1 << 16];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, in)) > 0) fwrite(buf, 1, n, f);
        fclose(in);
    }
    void finish() {
        const uint32_t cd = (uint32_t)ftell(f);
        for (size_t i = 0; i < ents.size(); i++) {
            string h;
            put32(h, 0x02014b50); put16(h, 20); put16(h, 20); put16(h, 0); put16(h, 0); put16(h, 0); put16(h, 0x21);
            put32(h, ents[i].crc); put32(h, ents[i].size); put32(h, ents[i].size); put16(h, (unsigned)ents[i].name.size());
            put16(h, 0); put16(h, 0); put16(h, 0); put16(h, 0); put32(h, 0); put32(h, ents[i].off);
            fwrite(h.data(), 1, h.size(), f);
            fwrite(ents[i].name.data(), 1, ents[i].name.size(), f);
        }
        const uint32_t cdsize = (uint32_t)ftell(f) - cd;
        string e;
        put32(e, 0x06054b50); put16(e, 0); put16(e, 0); put16(e, (unsigned)ents.size()); put16(e, (unsigned)ents.size());
        put32(e, cdsize); put32(e, cd); put16(e, 0);
        fwrite(e.data(), 1, e.size(), f);
        fclose(f);
    }
};

static string xml_esc(const string &s) {
    string o;
    for (size_t i = 0; i < s.size(); i++) {
        const unsigned char c = (unsigned char)s[i];
        if (c == '&') o += "&amp;"; else if (c == '<') o += "&lt;"; else if (c == '>') o += "&gt;"; else if (c == '"') o += "&quot;";
        else if (c < 0x20 && c != '\t' && c != '\n' && c != '\r') continue;
        else o += (char)c;
    }
    return o;
}
static string col_name(int c) {                                       // 0 -> A
    string s;
    for (c++; c > 0; c = (c - 1) / 26) s = (char)('A' + (c - 1) % 26) + s;
    return s;
}

struct Cell {
    char t;                                                           // 'n' number, 's' text, 'b' bool, 'e' empty
    string s;                                                         // number token (verbatim) or text
    bool b;
    Cell() : t('e'), b(false) {}
};
static Cell C_str(const string &v) { Cell c; c.t = 's'; c.s = v; return c; }
static Cell C_num(double v) { Cell c; if (isnan_(v) || std::isinf(v)) return c; c.t = 'n'; c.s = fmt("%.15g", v); return c; }
static Cell C_int(long long v) { Cell c; c.t = 'n'; c.s = std::to_string(v); return c; }
static Cell C_bool(bool v) { Cell c; c.t = 'b'; c.b = v; return c; }
static Cell C_empty() { return Cell(); }
static bool is_number_token(const string &s) {
    if (s.empty()) return false;
    char *e = 0;
    strtod(s.c_str(), &e);
    if (*e != '\0') return false;
    for (size_t i = 0; i < s.size(); i++) { const char c = s[i]; if (!(isdigit((unsigned char)c) || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E')) return false; }
    return true;
}
// CSV field -> typed cell (text columns stay text; True/False -> bool; numeric tokens verbatim)
static Cell C_auto(const string &s, bool force_text) {
    if (s.empty()) return C_empty();
    if (force_text) return C_str(s);
    if (s == "True") return C_bool(true);
    if (s == "False") return C_bool(false);
    if (is_number_token(s)) { Cell c; c.t = 'n'; c.s = s; return c; }
    return C_str(s);
}

struct Sheet {
    string name, tmp;
    FILE *f;
    uint32_t crc, size;
    int nrow;
    Sheet(const string &nm, const string &tmpdir, int idx) : name(nm), tmp(tmpdir + "/sheet" + std::to_string(idx) + ".xml"), f(fopen(tmp.c_str(), "wb")), crc(0), size(0), nrow(0) {
        if (!f) die("cannot write " + tmp);
        emit("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
             "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/></sheetView></sheetViews><sheetData>\n");
    }
    void emit(const string &s) { fwrite(s.data(), 1, s.size(), f); crc = crc_update(crc, s.data(), s.size()); size += (uint32_t)s.size(); }
    void row(const vector<Cell> &cells, bool header = false) {
        nrow++;
        string o = "<row r=\"" + std::to_string(nrow) + "\">";
        for (size_t i = 0; i < cells.size(); i++) {
            const Cell &c = cells[i];
            if (c.t == 'e') continue;
            const string ref = col_name((int)i) + std::to_string(nrow);
            const string st = header ? " s=\"1\"" : "";
            if (c.t == 'n') o += "<c r=\"" + ref + "\"" + st + "><v>" + c.s + "</v></c>";
            else if (c.t == 'b') o += "<c r=\"" + ref + "\" t=\"b\"" + st + "><v>" + (c.b ? "1" : "0") + "</v></c>";
            else o += "<c r=\"" + ref + "\" t=\"inlineStr\"" + st + "><is><t xml:space=\"preserve\">" + xml_esc(c.s) + "</t></is></c>";
        }
        o += "</row>\n";
        emit(o);
    }
    void header_row(const vector<string> &h) { vector<Cell> c; for (size_t i = 0; i < h.size(); i++) c.push_back(C_str(h[i])); row(c, true); }
    void close() { emit("</sheetData></worksheet>"); fclose(f); f = 0; }
};

static const int ROW_LIMIT = 1000000;   // Excel: 1,048,576 rows per sheet

struct Book {
    string tmpdir;
    vector<Sheet *> sheets;
    explicit Book(const string &t) : tmpdir(t) { mkdir_p(t); crc_init(); }
    Sheet *add(const string &name) { sheets.push_back(new Sheet(name, tmpdir, (int)sheets.size() + 1)); return sheets.back(); }
    void save(const string &path) {
        for (size_t i = 0; i < sheets.size(); i++) if (sheets[i]->f) sheets[i]->close();
        Zip z(path);
        string ct = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                    "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                    "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
                    "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>";
        for (size_t i = 0; i < sheets.size(); i++) ct += "<Override PartName=\"/xl/worksheets/sheet" + std::to_string(i + 1) + ".xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>";
        ct += "</Types>";
        z.add_blob("[Content_Types].xml", ct);
        z.add_blob("_rels/.rels", "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                                  "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>");
        string wb = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
                    "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>";
        string rel = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">";
        for (size_t i = 0; i < sheets.size(); i++) {
            wb += "<sheet name=\"" + xml_esc(sheets[i]->name) + "\" sheetId=\"" + std::to_string(i + 1) + "\" r:id=\"rId" + std::to_string(i + 1) + "\"/>";
            rel += "<Relationship Id=\"rId" + std::to_string(i + 1) + "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet" + std::to_string(i + 1) + ".xml\"/>";
        }
        wb += "</sheets></workbook>";
        rel += "<Relationship Id=\"rId" + std::to_string(sheets.size() + 1) + "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/></Relationships>";
        z.add_blob("xl/workbook.xml", wb);
        z.add_blob("xl/_rels/workbook.xml.rels", rel);
        z.add_blob("xl/styles.xml", "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
                                    "<fonts count=\"2\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font><font><b/><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
                                    "<fills count=\"2\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill></fills>"
                                    "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
                                    "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
                                    "<cellXfs count=\"2\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/><xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\"/></cellXfs>"
                                    "<cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles></styleSheet>");
        for (size_t i = 0; i < sheets.size(); i++) z.add_file("xl/worksheets/sheet" + std::to_string(i + 1) + ".xml", sheets[i]->tmp, sheets[i]->crc, sheets[i]->size);
        z.finish();
        for (size_t i = 0; i < sheets.size(); i++) { remove(sheets[i]->tmp.c_str()); delete sheets[i]; }
        sheets.clear();
        rmdir(tmpdir.c_str());
    }
};

}  // namespace xl

static int cmd_workbook(int argc, char **argv) {
    using namespace xl;
    set<string> noval;
    noval.insert("--no-iter");
    Args A(argc, argv, 2, noval);
    if (A.pos.empty()) die("usage: llrp_tools workbook DIR [-o out.xlsx] [--no-iter] [--manifest manifest.tsv]\n"
                           "  sheets: Final_Summary, Rank_Summaries, All_Run_Level_Details, All_Iteration_Logs, Rank_Best_Routes, Operator_Stats, Anytime_Trace");
    const string D = A.pos[0];
    string out = A.get("-o", D + "/" + base_name(D) + ".xlsx");
    Tbl R = load_tbl(D, "run");
    if (R.rows.empty()) die("run.csv not found / empty: " + D);
    map<string, MEntry> man;
    if (A.has("--manifest")) { vector<MEntry> M = load_manifest(A.get("--manifest")); for (size_t i = 0; i < M.size(); i++) man[M[i].name] = M[i]; }
    Book bk(out + ".tmp");
    const int cI = R.col("Instance"), cA = R.col("Algorithm"), cSd = R.col("Seed"), cF = R.col("Feasible"), cL = R.col("Total Latency"), cB = R.col("Reference BKS"), cC = R.col("CPU Time"),
              cOD = R.col("Open Depots"), cNR = R.col("Number of Routes"), cRun = R.col("Run"), cIt = R.col("Iterations"), cLI = R.col("Last Improvement Iteration"), cSt = R.col("Stop Reason"),
              cGap = R.col("Gap to BKS (%)"), cVC = R.col("Vehicle Capacity"), cNv = R.col("Nv"), cNg = R.col("Ng");
    vector<const vector<string> *> rs;
    for (size_t i = 0; i < R.rows.size(); i++) rs.push_back(&R.rows[i]);
    std::sort(rs.begin(), rs.end(), [&](const vector<string> *a, const vector<string> *b) {
        if ((*a)[cI] != (*b)[cI]) return nat_less((*a)[cI], (*b)[cI]);
        return atoi((*a)[cSd].c_str()) < atoi((*b)[cSd].c_str());
    });
    // ---- Final_Summary
    map<pair<string, string>, vector<const vector<string> *> > g;
    for (size_t i = 0; i < rs.size(); i++) g[std::make_pair((*rs[i])[cI], (*rs[i])[cA])].push_back(rs[i]);
    vector<pair<string, string> > gk;
    for (map<pair<string, string>, vector<const vector<string> *> >::iterator it = g.begin(); it != g.end(); ++it) gk.push_back(it->first);
    std::sort(gk.begin(), gk.end(), [](const pair<string, string> &a, const pair<string, string> &b) { return a.first != b.first ? nat_less(a.first, b.first) : a.second < b.second; });
    Sheet *ws = bk.add("Final_Summary");
    { const char *h[] = {"Instance", "Algorithm", "Total Rank Files", "Total Completed Runs", "Feasible Runs", "Feasibility Rate (%)", "Reference BKS", "Best Latency", "Gap to BKS (%)", "Mean Latency", "Std Latency",
                         "Mean CPU Time", "Total CPU Time", "Best Run", "Best Seed", "Best Open Depots", "Best Number of Routes", "Mean Gap to BKS (%)", "Mean Iterations", "Mean Last Improvement Iteration",
                         "Median Last Improvement Iteration", "Stop Reasons"};
      ws->header_row(vector<string>(h, h + 22)); }
    map<pair<string, string>, const vector<string> *> best_of;
    for (size_t q = 0; q < gk.size(); q++) {
        const vector<const vector<string> *> &v = g[gk[q]];
        vector<double> lat, cpu, its, lis;
        const vector<string> *br = 0;
        set<string> seeds;
        map<string, int> stops;
        for (size_t i = 0; i < v.size(); i++) {
            const vector<string> &r = *v[i];
            seeds.insert(r[cSd]);
            cpu.push_back(to_num(r[cC])); its.push_back(to_num(r[cIt])); lis.push_back(to_num(r[cLI])); stops[r[cSt]]++;
            if (to_bool(r[cF])) { lat.push_back(to_num(r[cL])); if (!br || to_num(r[cL]) < to_num((*br)[cL])) br = &r; }
        }
        const double bks = to_num((*v[0])[cB]);
        if (br) best_of[gk[q]] = br;
        string st;
        for (map<string, int>::iterator it = stops.begin(); it != stops.end(); ++it) st += (st.empty() ? "" : " ") + it->first + ":" + std::to_string(it->second);
        vector<Cell> c;
        c.push_back(C_str(gk[q].first)); c.push_back(C_str(gk[q].second)); c.push_back(C_int((long long)seeds.size())); c.push_back(C_int((long long)v.size())); c.push_back(C_int((long long)lat.size()));
        c.push_back(C_num(100.0 * lat.size() / v.size())); c.push_back(C_num(bks));
        c.push_back(lat.empty() ? C_empty() : C_num(min_of(lat))); c.push_back(lat.empty() ? C_empty() : C_num(100 * (min_of(lat) - bks) / bks));
        c.push_back(lat.empty() ? C_empty() : C_num(mean_of(lat))); c.push_back(lat.size() > 1 ? C_num(sd_of(lat)) : C_empty());
        c.push_back(C_num(mean_of(cpu))); c.push_back(C_num(sum_of(cpu)));
        c.push_back(br ? C_int(atoll((*br)[cRun].c_str())) : C_empty()); c.push_back(br ? C_int(atoll((*br)[cSd].c_str())) : C_empty());
        c.push_back(br ? C_str((*br)[cOD]) : C_empty()); c.push_back(br ? C_int(atoll((*br)[cNR].c_str())) : C_empty());
        c.push_back(lat.empty() ? C_empty() : C_num(100 * (mean_of(lat) - bks) / bks)); c.push_back(C_num(mean_of(its))); c.push_back(C_num(mean_of(lis))); c.push_back(C_num(median_of(lis))); c.push_back(C_str(st));
        ws->row(c);
    }
    // ---- Rank_Summaries
    ws = bk.add("Rank_Summaries");
    { const char *h[] = {"Instance", "Customers", "Candidate Depots", "Vehicle Capacity", "Vehicles Nv", "Open Depots Ng", "Total Completed Runs on This Rank", "Feasible Runs", "Feasibility Rate (%)", "Reference BKS",
                         "Best Latency", "Gap to BKS (%)", "Mean Latency", "Std Latency", "Mean CPU Time", "Total CPU Time", "Best Run", "Best Seed", "Best Open Depots", "Best Number of Routes", "MPI Rank", "MPI Size"};
      ws->header_row(vector<string>(h, h + 22)); }
    {
        set<int> sd;
        for (size_t i = 0; i < rs.size(); i++) sd.insert(atoi((*rs[i])[cSd].c_str()));
        vector<int> seeds(sd.begin(), sd.end());
        for (size_t i = 0; i < rs.size(); i++) {
            const vector<string> &r = *rs[i];
            const bool ok = to_bool(r[cF]);
            const bool hm = man.count(r[cI]) > 0;
            vector<Cell> c;
            c.push_back(C_str(r[cI])); c.push_back(hm ? C_int(man[r[cI]].n) : C_empty()); c.push_back(hm ? C_int(man[r[cI]].m) : C_empty()); c.push_back(C_auto(r[cVC], false));
            c.push_back(C_auto(r[cNv], false)); c.push_back(C_auto(r[cNg], false)); c.push_back(C_int(1)); c.push_back(C_int(ok ? 1 : 0)); c.push_back(C_int(ok ? 100 : 0));
            c.push_back(C_auto(r[cB], false)); c.push_back(C_auto(r[cL], false)); c.push_back(C_auto(r[cGap], false)); c.push_back(C_auto(r[cL], false)); c.push_back(C_empty());
            c.push_back(C_auto(r[cC], false)); c.push_back(C_auto(r[cC], false)); c.push_back(C_auto(r[cRun], false)); c.push_back(C_auto(r[cSd], false)); c.push_back(C_str(r[cOD]));
            c.push_back(C_auto(r[cNR], false));
            c.push_back(C_int((long long)(std::find(seeds.begin(), seeds.end(), atoi(r[cSd].c_str())) - seeds.begin()))); c.push_back(C_int((long long)seeds.size()));
            ws->row(c);
        }
    }
    // ---- All_Run_Level_Details
    ws = bk.add("All_Run_Level_Details");
    ws->header_row(R.hdr);
    for (size_t i = 0; i < rs.size(); i++) {
        vector<Cell> c;
        for (size_t k = 0; k < R.hdr.size(); k++) {
            const string &h = R.hdr[k];
            c.push_back(C_auto((*rs[i])[k], h == "Instance" || h == "Algorithm" || h == "Open Depots" || h == "Stop Reason"));
        }
        ws->row(c);
    }
    // ---- All_Iteration_Logs (streamed; split in parts of 1,000,000 rows)
    if (!A.has("--no-iter")) {
        vector<string> files = kind_files(D, "iter");
        int part = 0;
        Sheet *cur = 0;
        vector<string> hdr = hdr_vec(HDR_ITER);
        for (size_t fi = 0; fi < files.size(); fi++) {
            vector<string> h;
            scan_csv(files[fi], hdr, h, [&](const vector<string> &r) {
                if (!cur || cur->nrow >= ROW_LIMIT) { part++; cur = bk.add(part == 1 ? "All_Iteration_Logs" : "All_Iteration_Logs_" + std::to_string(part)); cur->header_row(hdr); }
                vector<Cell> c;
                for (size_t k = 0; k < r.size(); k++) { const string &hh = hdr[k < hdr.size() ? k : hdr.size() - 1]; c.push_back(C_auto(r[k], hh == "Instance" || hh == "Algorithm" || hh == "Mode" || hh == "Open Depots")); }
                cur->row(c);
            });
        }
    }
    // ---- Rank_Best_Routes
    Tbl RT = load_tbl(D, "routes");
    if (!RT.rows.empty()) {
        const int rI = RT.col("Instance"), rA = RT.col("Algorithm"), rS = RT.col("Seed");
        map<pair<string, string>, vector<const vector<string> *> > byk;
        for (size_t i = 0; i < RT.rows.size(); i++) byk[std::make_pair(RT.rows[i][rI] + "\x01" + RT.rows[i][rA], RT.rows[i][rS])].push_back(&RT.rows[i]);
        ws = bk.add("Rank_Best_Routes");
        // column order of the delivered Excel layout: Seed is the LAST column
        static const char *ordn[] = {"Instance", "Algorithm", "Route ID", "Depot", "Customers", "Arrival Times", "Number of Customers", "Load", "Route Latency", "Open Route Distance", "Seed"};
        vector<string> outh; vector<int> outc;
        for (size_t k = 0; k < sizeof(ordn) / sizeof(ordn[0]); k++) { outh.push_back(ordn[k]); outc.push_back(RT.col(ordn[k])); }
        ws->header_row(outh);
        for (size_t q = 0; q < gk.size(); q++) {
            if (!best_of.count(gk[q])) continue;
            const string seed = (*best_of[gk[q]])[cSd];
            map<pair<string, string>, vector<const vector<string> *> >::iterator f = byk.find(std::make_pair(gk[q].first + "\x01" + gk[q].second, seed));
            if (f == byk.end()) continue;
            for (size_t i = 0; i < f->second.size(); i++) {
                vector<Cell> c;
                for (size_t k = 0; k < outh.size(); k++) { const string &h = outh[k]; c.push_back(C_auto((*f->second[i])[outc[k]], h == "Instance" || h == "Algorithm" || h == "Customers" || h == "Arrival Times")); }
                ws->row(c);
            }
        }
    }
    // ---- Operator_Stats (instance x operator, all seeds)
    Tbl O = load_tbl(D, "ops");
    if (!O.rows.empty()) {
        struct Acc { int n; double v[8]; };
        map<pair<pair<string, string>, string>, Acc> agg;
        vector<pair<pair<string, string>, string> > order;
        const int oI = O.col("Instance"), oA = O.col("Algorithm"), oO = O.col("Operator");
        for (size_t i = 0; i < O.rows.size(); i++) {
            pair<pair<string, string>, string> k = std::make_pair(std::make_pair(O.rows[i][oI], O.rows[i][oA]), O.rows[i][oO]);
            if (!agg.count(k)) { Acc a; a.n = 0; for (int q = 0; q < 8; q++) a.v[q] = 0; agg[k] = a; order.push_back(k); }
            Acc &a = agg[k];
            a.n++;
            for (int q = 0; q < 8; q++) { const double x = to_num(O.rows[i][O.col(OPCOLS[q])]); a.v[q] += isnan_(x) ? 0 : x; }
        }
        map<pair<string, string>, double> tg, tc;
        for (size_t i = 0; i < order.size(); i++) { tg[order[i].first] += agg[order[i]].v[3]; tc[order[i].first] += agg[order[i]].v[5]; }
        std::stable_sort(order.begin(), order.end(), [&](const pair<pair<string, string>, string> &a, const pair<pair<string, string>, string> &b) {
            if (a.first.first != b.first.first) return nat_less(a.first.first, b.first.first);
            if (a.first.second != b.first.second) return a.first.second < b.first.second;
            return agg[a].v[3] > agg[b].v[3];
        });
        ws = bk.add("Operator_Stats");
        { const char *h[] = {"Instance", "Algorithm", "Operator", "Seeds", "Calls", "Evaluations", "Applied", "Hit Rate (%)", "Gain Latency", "Share of Latency Gain (%)", "Gain Objective", "CPU Seconds", "CPU Share (%)",
                             "Gain per CPU Second", "Best-Iteration Applied", "Best-Iteration Gain Latency"};
          ws->header_row(vector<string>(h, h + 16)); }
        for (size_t i = 0; i < order.size(); i++) {
            const Acc &a = agg[order[i]];
            const double gsum = tg[order[i].first], cc = tc[order[i].first];
            vector<Cell> c;
            c.push_back(C_str(order[i].first.first)); c.push_back(C_str(order[i].first.second)); c.push_back(C_str(order[i].second)); c.push_back(C_int(a.n));
            c.push_back(C_num(a.v[0])); c.push_back(C_num(a.v[1])); c.push_back(C_num(a.v[2])); c.push_back(a.v[0] ? C_num(100 * a.v[2] / a.v[0]) : C_empty());
            c.push_back(C_num(a.v[3])); c.push_back(gsum ? C_num(100 * a.v[3] / gsum) : C_empty()); c.push_back(C_num(a.v[4])); c.push_back(C_num(a.v[5]));
            c.push_back(cc ? C_num(100 * a.v[5] / cc) : C_empty()); c.push_back(a.v[5] ? C_num(a.v[3] / a.v[5]) : C_empty()); c.push_back(C_num(a.v[6])); c.push_back(C_num(a.v[7]));
            ws->row(c);
        }
    }
    // ---- Anytime_Trace
    Tbl X = load_tbl(D, "trace");
    if (!X.rows.empty()) {
        const int tI = X.col("Instance"), tS = X.col("Seed"), tIt = X.col("Iteration");
        vector<const vector<string> *> v;
        for (size_t i = 0; i < X.rows.size(); i++) v.push_back(&X.rows[i]);
        std::stable_sort(v.begin(), v.end(), [&](const vector<string> *a, const vector<string> *b) {
            if ((*a)[tI] != (*b)[tI]) return nat_less((*a)[tI], (*b)[tI]);
            if ((*a)[tS] != (*b)[tS]) return atoi((*a)[tS].c_str()) < atoi((*b)[tS].c_str());
            return atoi((*a)[tIt].c_str()) < atoi((*b)[tIt].c_str());
        });
        Sheet *cur = 0;
        int part = 0;
        for (size_t i = 0; i < v.size(); i++) {
            if (!cur || cur->nrow >= ROW_LIMIT) { part++; cur = bk.add(part == 1 ? "Anytime_Trace" : "Anytime_Trace_" + std::to_string(part)); cur->header_row(X.hdr); }
            vector<Cell> c;
            for (size_t k = 0; k < X.hdr.size(); k++) c.push_back(C_auto((*v[i])[k], X.hdr[k] == "Instance" || X.hdr[k] == "Algorithm"));
            cur->row(c);
        }
    }
    bk.save(out);
    printf("yazildi: %s\n", out.c_str());
    return 0;
}

#endif
