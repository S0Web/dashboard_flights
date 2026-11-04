# Dashboard Trafic aérien NYC — Streamlit + Supabase

## Arborescence
```
trafic_aerien/
├── app.py
├── requirements.txt
└── .streamlit/
    └── secrets.toml      <- créé à partir de secrets.toml.example
```

## Lancer en local
```bash
pip install -r requirements.txt
mkdir .streamlit
cp secrets.toml.example .streamlit/secrets.toml   # puis remplir host / username / password
streamlit run app.py
```

## Récupérer les identifiants Supabase
Projet Supabase > bouton **Connect** > **Connection String** > **Session pooler**.
La chaîne ressemble à :
`postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
→ reporter chaque morceau dans `secrets.toml`.
Mot de passe oublié : Project Settings > Database > Reset database password.

## Contenu du dashboard
Filtres (barre latérale) : aéroport de départ, compagnies, période.
- **KPI** : vols, destinations, retard moyen, % à l'heure, % annulés
- **Vue d'ensemble** : vols par mois et aéroport, répartition, statut des vols
- **Retards** : par heure programmée, par jour de semaine, distribution
- **Compagnies** : volume, ponctualité vs retard, tableau récapitulatif
- **Destinations** : carte des USA + top N
- **Météo** : retard moyen selon visibilité / vent / pluie / température / humidité
- **Flotte** : constructeurs, retard selon l'âge de l'avion

Toutes les agrégations sont faites en SQL côté Postgres (on ne télécharge jamais
les 250 000 vols) et mises en cache 1 h.

## Déployer (Streamlit Community Cloud)
1. Pousser `app.py` + `requirements.txt` sur GitHub (pas `secrets.toml` !).
2. share.streamlit.io > New app > choisir le repo.
3. Advanced settings > Secrets : coller le contenu de `secrets.toml`.
