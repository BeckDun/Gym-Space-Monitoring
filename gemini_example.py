from google import genai
from google.genai import types

# Only for videos of size <20Mb
video_file_name = "Man_Falling_in_Gym_Video.mp4"
video_bytes = open(video_file_name, 'rb').read()

client = genai.Client()
response = client.models.generate_content(
    model='gemini-3-flash-preview',
    contents=types.Content(
        parts=[
            types.Part(
                inline_data=types.Blob(data=video_bytes, mime_type='video/mp4')
            ),
            types.Part(text='Is the man distressed? Give a rating 1-10 if they need help.         give me the output in a message like: Distress: *1-10*, Fall Likeleyhood: *1-10*')
        ]
    )
)
print(response.text)
