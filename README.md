My idea for this semester's project is to create an a dashboard for viewing results from the save game files of my favorite strategy game, Europa Universalis IV. The user flow would be uploading their save file to the service, which would process it and provide meaningful data about your save to view in a web interface. You could, for instance, query what nation you reached +1000 income the fastest, or see your most/least played nations.
The project would touch on the three "pillars" of AWS we've looked at so far:
•	EC2 for processing the save file and extracting the relevant data.
•	DB for storing the relevant data.
•	S3 for storing the original save file, in case more data needs to be processed later.
There is a ton of data in the save file that can be parsed out. I found one tool that does this, eu4save. It's coded in Rust, which I've never used, so I figure this is a good opportunity to try it out.
