# management/commands/view_random_embedding.py
import numpy as np
import random
from django.core.management.base import BaseCommand
from movie.models import Movie  # Asegúrate de usar el nombre correcto de tu app

class Command(BaseCommand):
    help = "Visualiza los embeddings de una película seleccionada al azar"

    def handle(self, *args, **kwargs):
        # ✅ Seleccionar una película al azar
        movies = Movie.objects.all()
        if not movies.exists():
            self.stdout.write(self.style.ERROR("❌ No hay películas en la base de datos."))
            return

        movie = random.choice(movies)
        self.stdout.write(self.style.SUCCESS(f"🎥 Película seleccionada: {movie.title}"))

        # ✅ Convertir los embeddings de binario a NumPy array
        try:
            emb = np.frombuffer(movie.emb, dtype=np.float32)
            self.stdout.write(f"📊 Embeddings: {emb}")
        except Exception as e:
            self.stderr.write(f"❌ Error al convertir los embeddings: {e}")