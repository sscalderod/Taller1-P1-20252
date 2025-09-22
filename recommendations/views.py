from django.shortcuts import render
from openai import OpenAI
from dotenv import load_dotenv
import os
import numpy as np
from movie.models import Movie  

# Create your views here.
load_dotenv("./openAI.env")
client = OpenAI(api_key=os.environ.get("openai_apikey"))

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def recommend(request):
    recommendation = None

    if request.method == "POST":
        prompt = request.POST.get("prompt")

        # ✅ Generar embedding del prompt
        response = client.embeddings.create(
            input=[prompt],
            model="text-embedding-3-small"
        )
        prompt_emb = np.array(response.data[0].embedding, dtype=np.float32)

        # ✅ Buscar la película más similar
        best_movie, max_similarity = None, -1
        for movie in Movie.objects.exclude(emb__isnull=True):
            movie_emb = np.frombuffer(movie.emb, dtype=np.float32)
            similarity = cosine_similarity(prompt_emb, movie_emb)

            if similarity > max_similarity:
                max_similarity = similarity
                best_movie = movie

        if best_movie:
            recommendation = {
                "title": best_movie.title,
                "description": best_movie.description,
                "image": best_movie.image.url if best_movie.image else None,
                "score": round(max_similarity, 4),
            }

    return render(request, "recommend.html", {"recommendation": recommendation})