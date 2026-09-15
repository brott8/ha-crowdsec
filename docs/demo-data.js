/* Deterministic demo dataset for the crowdsec-card harness.
 * Mimics the `decisions` attribute of the CrowdSec sensor, geo fields
 * included (as produced by the ip-api.com enrichment). */

const SPEC = [
  { cc: "CN", count: 24, lat: 34.8, lon: 104.2, prefixes: ["45.83.221", "218.92.0", "61.177.173", "222.186.30"],
    asns: [["CHINANET-BACKBONE", 4134], ["CHINA169-BACKBONE", 4837]] },
  { cc: "US", count: 16, lat: 39.8, lon: -98.6, prefixes: ["64.62.197", "205.210.31", "198.235.24"],
    asns: [["HURRICANE", 6939], ["PAN0001", 396982], ["DIGITALOCEAN-ASN", 14061]] },
  { cc: "RU", count: 12, lat: 55.7, lon: 37.6, prefixes: ["185.220.101", "5.188.206", "193.32.162"],
    asns: [["SELECTEL", 49505], ["PIN-AS", 34665]] },
  { cc: "BR", count: 7, lat: -14.2, lon: -51.9, prefixes: ["177.54.144", "45.190.220"],
    asns: [["TELEFONICA BRASIL", 27699], ["CLARO SA", 28573]] },
  { cc: "IN", count: 6, lat: 21.0, lon: 78.0, prefixes: ["103.21.124", "117.247.108"],
    asns: [["BHARTI-AIRTEL", 9498], ["BSNL-NIB", 9829]] },
  { cc: "VN", count: 5, lat: 16.0, lon: 107.8, prefixes: ["14.161.30", "113.161.72"],
    asns: [["VIETEL-AS-AP", 7552], ["VNPT-AS-VN", 45899]] },
  { cc: "DE", count: 4, lat: 51.2, lon: 10.4, prefixes: ["45.9.148", "194.55.224"],
    asns: [["HETZNER-AS", 24940], ["M247", 9009]] },
  { cc: "NL", count: 3, lat: 52.2, lon: 5.5, prefixes: ["89.248.165", "45.135.232"],
    asns: [["RECYBER", 202425], ["IPV LTD", 57717]] },
  { cc: "FR", count: 2, lat: 46.6, lon: 2.4, prefixes: ["51.68.11", "82.65.104"],
    asns: [["OVH", 16276], ["PROXAD Free SAS", 12322]] },
  { cc: "GB", count: 2, lat: 54.4, lon: -2.9, prefixes: ["141.98.81", "51.140.35"],
    asns: [["M247 Europe", 9009], ["MICROSOFT-CORP", 8075]] },
  { cc: "KR", count: 1, lat: 36.4, lon: 127.9, prefixes: ["211.219.24"],
    asns: [["KIXS-AS-KR Korea Telecom", 4766]] },
];

const SCENARIOS = [
  "crowdsecurity/ssh-bf",
  "crowdsecurity/ssh-slow-bf",
  "crowdsecurity/http-probing",
  "crowdsecurity/http-bad-user-agent",
  "crowdsecurity/http-crawl-non_statics",
  "crowdsecurity/http-sensitive-files",
  "crowdsecurity/http-open-proxy",
  "crowdsecurity/CVE-2017-9841",
];

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function generateDecisions(seed = 42) {
  const rnd = mulberry32(seed);
  const decisions = [];
  let id = 1000;
  for (const c of SPEC) {
    let lastIp = null;
    for (let i = 0; i < c.count; i++) {
      const prefix = c.prefixes[Math.floor(rnd() * c.prefixes.length)];
      const [asName, asNumber] = c.asns[Math.floor(rnd() * c.asns.length)];
      const total = 300 + Math.floor(rnd() * 14100); // 5 min .. ~4 h remaining
      const h = Math.floor(total / 3600);
      const m = Math.floor((total % 3600) / 60);
      const s = (total % 60) + Math.round(rnd() * 900) / 1000;
      // Repeat offenders: some IPs carry several decisions (one per scenario),
      // like real CrowdSec data - the card groups them.
      const value = lastIp && rnd() < 0.35 ? lastIp : `${prefix}.${1 + Math.floor(rnd() * 253)}`;
      lastIp = value;
      // A couple of non-default cases so the card badges show up in captures:
      // one captcha remediation and one manual cscli ban, with long durations
      // so they sort near the top of the list.
      const type = c.cc === "FR" && i === 0 ? "captcha" : "ban";
      const origin = c.cc === "DE" && i === 0 ? "cscli" : "crowdsec";
      let duration = `${h ? h + "h" : ""}${m}m${s}s`;
      if (type === "captcha") duration = "4h30m0s";
      if (origin === "cscli") duration = "23h59m30s";
      decisions.push({
        id: id++,
        origin,
        scope: "Ip",
        type,
        value,
        scenario: origin === "cscli" ? "manual" : SCENARIOS[Math.floor(rnd() * SCENARIOS.length)],
        duration,
        country: c.cc,
        latitude: Math.round((c.lat + (rnd() - 0.5) * 6) * 100) / 100,
        longitude: Math.round((c.lon + (rnd() - 0.5) * 6) * 100) / 100,
        as_name: asName,
        as_number: asNumber,
      });
    }
  }
  return decisions;
}
