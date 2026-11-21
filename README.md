# print-explosion-3d
Remember Print Explosion? Time to have some fun with AI and 3D prints.

# Motivation
Back in the day, my mom would run Print Explosion Deluxe on her iMac G3 and print custom Avery labels for pretty much everything. It was her jam, and she really misses being able to use it. Also, Avery labels and ink are really expensive.

My parents have always been interested in 3D printing, but it would be way too hard to teach them how to, say, unclog a hotend. I bought them a Bambu Lab A1 Mini because I was confident they could happily use it and maintain it. My mom loves it and is using the Bambu web customizer for parametric SCAD files. There are lots of AI -> STL programs out there, but they all require some sort of login or technical know-how. I want to make her an easy-to-install, update, and use Mac app where she can make fun stuff and get creative.

# Brainstorm
I bought $20 of Anthropic API credits while I was messing around with chatbots, and they will expire soon. I want to use those credits along with a simple OpenSCAD-like GUI to make a prompt -> model workflow.

## Chatbot (left panel)
A jargon-free designer that uses publicly available OpenSCAD skills to generate and iterate on SCAD files. The bot should be able to interpret items from attached images, as well as be flexible with units and design terminology.

### Design focus
- Simple prints with minimal or easy-to-remove supports, with optimized print bed orientation
- Good first layer structure to allow for prints with no brim/skirt, as well as easy bed release
- Parametric values for easy tweaking of designs
- New project button
- Delete project button
- Auto-save status info

### File management
- Create a workspace folder and intelligently stash away resource files and memories so that users can conversationally resume or start new projects without using a file browser
- Clean up stale assets and simplify structure as necessary

### Considerations
- Use simple regex or other string processing when possible to prevent burning credits faster than necessary
- Minimize token usage by clarifying intent before performing longer tasks

## Viewer (main panel)
- When the user clicks a Generate button, the viewer updates and renders the model
- Errors are captured and fed back into the chat panel as an auto-iteration
- No gridlines
- Simple color palette and shadowing that can be configured via a `.env` file
- Viewer spins slowly by itself, and the user can click the model to pause it
- Zoom and angle sliders allow users to get a different perspective without needing to learn CAD controls

## Parametric editor (right panel)
- Simplified OpenSCAD panel with easy-to-use text entries and dropdowns
- Export STL button
- Open in Bambu Studio button that opens the file in a new project via CLI or another Apple-style method

## Other
- Open to the last project with stashed chat history
- Abstract AI calls so it is easy to plug in other providers if someone wants to
- Research the best framework for the workflow to allow for a single-window application
- App deployment can rely on `git pull` for now
