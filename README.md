# Gemma-AI-twitch-style-chat
very bad AI twitch chat that gets screenshots of your screen and reacts to it.

Hello. This is an old project that I worked on for a few days to try and expriment with local LLM vision models. I do not plan to update this but it is here to be explored if you choose to do so.
Code was created with help from Google Gemini

This code uses gemma3:12b on ollama to read the image and generate batch reactions that are displayed into the chat at random intervals. It takes a screenshot every time a new batch of messages are generates and gets right to work on the next batch. You can start and stop generating the messages by pressing '0' on your keyboard. There is also an option to keep the screen on top for single monitor users. The screenshot used to generate the next batch of reactions is also displayed on the top of the window.

REQUIREMENTS
- System strong enough to run a vision LLM model, prompts are currently tailored for gemma3:12b. Code was created and tested on rx7900gre (16GB VRAM)
- ollama with your preferred model downloaded
- dependencies for python(keyboard, mss, pillow, ollama)

Instructions
- launch ollama into the background
- run the python file
- press '0' to start capturing and get messages
- press '0' again to stop. current version still sends many messages after you stop but GPU stops inference right after current batch of messages have been generated.
- other features should be self explanatory when you run the program.

Known issues
- chat continues to move for a long time after stopping  
  -  I have no idea why this happens but is not crucial so I might look into it if I have time
- slow message generation
  - it takes some time for mine to start popping up, but keeps running once the first ones get running. Maybe run this on a smaller model or get more vram?
 
Final notes
I dont know if I want to improve this or just abandon it, but if I find the time eventually I'll try.
