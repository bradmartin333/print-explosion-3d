# print-explosion-3d
remember print explosion? time to have some fun with AI and 3d prints

# motivation
back in the day, my mom would run Print Explosion Deluxe on her iMac G3 and print custom Avery labels for pretty much everything. it was her jam and she really misses being able to use it. also, Avery labels and ink are really expensive.
my parents have always been interested in 3d printing, but it would be way too hard to teach them how to, say, unclog a hotend. i bought them a Bambu Lab A1 Mini as i was confident they could happily use it and maintain it. my mom loves it and is using the Bambu web customizer for parametric scad files. there are lots of AI -> STL programs out there, but they all require some sort of login or techincal know-how. i want to make her an easy to install, update and use mac app where she can make fun stuff and get creative.

# brainstorm
i bought $20 of Anthropic API credits while i was messing around with chatbots and they will expire soon. i want to use those credits along with a simple openSCAD-like GUI to make a prompt -> model workflow.

## chatbot (left panel)
a jargon-free designer that uses publically available openSCAD skills to generate and iterate on scad files. the bot should be able to interpret items from attached images as well as be flexible with units / design terminology.

### design focus
- simple prints with minimal or easy-to-remove supports with optimized print bed orientation
- good first layer structure to allow for prints with no brim/skirt as well as easy bed release
- parametric values for easy tweaking of design
- new project button
- delete project button
- auto-save status info

### file management
- create a workspace folder and intelligently stash away resource files and memories so that users can conversationally resume or start new projects without using a file browser
- cleanup stale assets and simplify structure as necessary

### considerations
- use simple regex or other string processing when possible to prevent burning credits faster then necessary
- minimize token usage by clarifying intent before performing longer tasks

## viewer (main panel)
- when user clicks a generate button, the viewer updates and renders the model
- errors are captured and fed back into the chat panel as an auto-iteration
- no gridlines
- simple color pallete and shadowing that can be configures via a .env file
- viewer spins slowly by itself and user can click on the model to pause it
- zoom and angle sliders allow for users to get a different perspective without needing to learn CAD controls

## parametric editor (right panel)
- simplified openSCAD panel with easy to use text entries and dropdowns
- export STL button
- open in Bambu Studio button that opens file in new project via CLI or other apple-style method

## other
- open to last project with stashed chat history
- abstract AI calls so it is easy to plug in other providers if someone wants to
- need to research the best framework for the workflow to allow for a single window application
- app deployment can rely on `git pull` for now
