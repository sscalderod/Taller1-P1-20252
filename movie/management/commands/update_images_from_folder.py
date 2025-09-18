import os as _os
import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches

from django.conf import settings
from django.core.management.base import BaseCommand
from movie.models import Movie

# ---------- Utilidades de normalización ----------

_GENERIC_BASENAMES = {
    "captura", "sintitulo", "sin titulo", "sintítul", "unnamed", "default",
    "image", "img", "photo", "foto", "screenshot"
}

_PREFIXES = (
    "m_", "poster_", "cover_", "img_", "image_", "foto_", "screenshot_",
    "cap_", "captura_", "sin_titulo_", "sintitulo_", "unnamed_"
)

def strip_prefixes(name: str) -> str:
    n = name
    for p in _PREFIXES:
        if n.startswith(p):
            n = n[len(p):]
    return n

def strip_numeric_suffix(name: str) -> str:
    # elimina _16, -2, (1), etc. al final
    n = re.sub(r"[\s_\-]*(\(\d+\)|\d+)$", "", name)
    return n

def normalize(s: str) -> str:
    # a minúsculas
    s = s.lower()
    # unicode → sin diacríticos
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    # caracteres “raros”/mojibake muy comunes → reemplazos suaves
    s = s.replace("’", "'").replace("–", "-").replace("—", "-").replace("´", "'")
    # quita todo lo que no sea alfanumérico
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def normalize_filename_stem(stem: str) -> str:
    stem = strip_prefixes(stem)
    stem = strip_numeric_suffix(stem)
    return normalize(stem)

def is_generic_basename(stem: str) -> bool:
    n = normalize(stem)
    return any(token in n for token in (normalize(x) for x in _GENERIC_BASENAMES))

def similarity(a: str, b: str) -> float:
    # 0..1
    return SequenceMatcher(None, a, b).ratio()

# ---------- Comando ----------

class Command(BaseCommand):
    help = "Update movie images in the database from a folder"

    def handle(self, *args, **kwargs):
        base_media = getattr(settings, "MEDIA_ROOT", "media")
        images_folder = _os.path.join(base_media, "movie", "images")

        if not _os.path.exists(images_folder):
            self.stderr.write(f"Images folder '{images_folder}' not found.")
            return

        movies = list(Movie.objects.all())
        if not movies:
            self.stderr.write("No movies found in DB.")
            return

        # Mapas para búsqueda rápida
        title_norm_map = {}
        tokens_map = {}
        for m in movies:
            tn = normalize(m.title)
            title_norm_map[tn] = m
            # bolsa de tokens (para ‘contains’ flexibles)
            tokens_map[m] = re.findall(r"[a-z0-9]+", normalize(m.title))

        updated = 0
        skipped = 0

        for filename in _os.listdir(images_folder):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue

            stem = _os.path.splitext(filename)[0]

            # ignorar genéricos
            if is_generic_basename(stem):
                skipped += 1
                continue

            file_norm = normalize_filename_stem(stem)

            # 1) match exacto por normalizado
            found = title_norm_map.get(file_norm)

            # 2) contains simple (file_norm dentro del título o viceversa)
            if not found:
                for m in movies:
                    tnorm = normalize(m.title)
                    if file_norm and (file_norm in tnorm or tnorm in file_norm):
                        found = m
                        break

            # 3) fuzzy (difflib) — sube/baja el umbral según tu dataset
            if not found:
                candidates = list(title_norm_map.keys())
                # usa get_close_matches para shortlist
                shortlist = get_close_matches(file_norm, candidates, n=5, cutoff=0.72)
                best = None
                best_sim = 0.0
                for cand in shortlist:
                    sim = similarity(file_norm, cand)
                    if sim > best_sim:
                        best_sim = sim
                        best = cand
                if best and best_sim >= 0.76:
                    found = title_norm_map[best]

            # 4) token overlap heurístico (para títulos largos)
            if not found:
                best_m = None
                best_score = 0
                f_tokens = set(re.findall(r"[a-z0-9]+", file_norm))
                if f_tokens:
                    for m in movies:
                        mt = set(tokens_map[m])
                        # Jaccard simple
                        inter = len(f_tokens & mt)
                        union = len(f_tokens | mt) or 1
                        score = inter / union
                        if score > best_score:
                            best_score = score
                            best_m = m
                    if best_m and best_score >= 0.4:
                        found = best_m

            if not found:
                # Mensaje con algunas sugerencias cercanas
                sugg = get_close_matches(file_norm, list(title_norm_map.keys()), n=3, cutoff=0.6)
                if sugg:
                    human = ", ".join(title_norm_map[s].title for s in sugg)
                else:
                    # fallback: primeras 3 por similitud
                    scored = sorted(
                        ((m.title, similarity(file_norm, normalize(m.title))) for m in movies),
                        key=lambda x: x[1], reverse=True
                    )[:3]
                    human = ", ".join(t for t, _ in scored) if scored else "No suggestions"

                self.stderr.write(f"Movie not found for image: {filename}. Suggestions: {human}")
                continue

            # Si llegamos aquí, tenemos ‘found’
            try:
                found.image = f"movie/images/{filename}"
                found.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated image for: {found.title}"))
            except Exception as e:
                self.stderr.write(f"Failed to update image for {filename}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Finished updating images. Updated: {updated}, Skipped generic: {skipped}"
        ))