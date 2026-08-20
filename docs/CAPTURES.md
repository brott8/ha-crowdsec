# Regénérer les captures d'écran

Note de maintenance — volontairement absente du README.

[`screenshot-harness.html`](screenshot-harness.html) charge la **vraie carte**
du composant (`custom_components/crowdsec/www/crowdsec-card.js`) avec un
`hass` factice et le jeu de données de [`demo-data.js`](demo-data.js)
(82 bans répartis sur 11 pays, déterministe), puis Chrome headless
photographie chaque page :

```bash
chrome --headless=new --disable-gpu --allow-file-access-from-files \
  --hide-scrollbars --force-device-scale-factor=2 --window-size=940,480 \
  --screenshot=hero-light.png "screenshot-harness.html?page=hero&mode=light"
```

| Page | Contenu | Taille fenêtre |
|---|---|---|
| `hero` | carte large 2 colonnes (liste + mapmonde) | 940,480 |
| `views` | `view: auto` (empilée) et `view: map` côte à côte (étroit) | 840,660 |
| `palettes` | les 3 palettes du dégradé, `view: map` | 1260,485 |
| `compact` | `view: list`, liste seule | 460,440 |

Chaque page existe en `mode=light` et `mode=dark` (`&lang=en` disponible).
Les fichiers vont dans `images/` sous le nom `<page>-<mode>.png`.

La mapmonde vient de `custom_components/crowdsec/www/world-map.js`, généré
par [`../tools/generate_world_map.py`](../tools/generate_world_map.py)
(Natural Earth 110m via world-atlas, projection équirectangulaire,
Antarctique retirée, longitudes déroulées à l'antiméridien pour la Russie et
les Aléoutiennes). Les drapeaux sont chargés depuis flagcdn.com — les
captures nécessitent donc le réseau.
