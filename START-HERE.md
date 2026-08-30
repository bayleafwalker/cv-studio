# A stupidly simple little CV generator

This little app runs on your own computer. Your CV is not uploaded anywhere.

## The first time on Windows

1. On the project’s GitHub page, open **Releases** and download
   `cv-studio-windows.zip` from the latest release’s **Assets** section. You do
   not need Git or a GitHub account.
2. Open your Downloads folder, right-click the ZIP file and choose **Extract All**.
   Open the extracted `cv-studio` folder.
3. Install **Python 3** from [python.org](https://www.python.org/downloads/). During installation, tick **Add Python to PATH** if you see that choice.
4. Double-click `start-windows.bat`.
5. Your web browser should open the editor. If it does not, open this address yourself: `http://127.0.0.1:8765`.

Leave the black window open while using the editor. When you are finished,
close that window.

## Getting the newest version later

Double-click `update-windows.bat`. It downloads the latest release and replaces
the app files. Your own CV files are never touched. Afterwards start the app
again with `start-windows.bat`.

## The easy way: let ChatGPT write the first draft

1. Start the app and click **Copy example for ChatGPT**.
2. Paste into ChatGPT together with your old CV text or a job advert, and ask
   it to fill in the CV. The copied text already tells it to answer with the
   complete JSON only.
3. Save the answer as a file ending in `.json`, for example `my-cv.json`.
   (In ChatGPT, use the copy button on the code block, paste into Notepad and
   choose Save as… with the name in quotes: `"my-cv.json"`.)
4. Back in the app, click **Open a CV file…** and pick that file, or simply
   drag the file onto the app window. It opens straight away and is saved as
   its own CV, named after the file. No typing of names needed.

You can also click **Open CV folder** and put `.json` files there. The app
notices new files within a few seconds and offers to open them.

If a file is broken, the app says so in a red box and tells you what is wrong
and where (for example “not valid JSON at line 12”). Paste that message back
to ChatGPT and ask for the complete corrected file.

## Editing your CV

1. At the top of the form, choose which **CV** to work on. **Make a copy of
   this CV** creates a separate version for another job type.
2. Choose a style: **Classic two-column** is compact; **Modern single-column**
   matches the usual published CV style.
3. Replace the text in “About you”, “Contact details”, and the cards below.
   Add achievements one per line. Changes are saved automatically.
4. The page on the right updates as you type and scrolls to the part you are
   editing. Red lines show where each A4 page ends. Use **Move up** and
   **Move down** to choose the section order. Tick **Start this section on a
   new page** if you want a deliberate page break.
5. When ready, click **Save as PDF**. On most computers the normal print
   window opens; choose **Save as PDF** (or **Microsoft Print to PDF**) as the
   printer and click Save. That is the normal Windows way to make a PDF.

## Where your work is saved

After the first change, the app creates `content/cv.local.json` (“My CV”).
Every other CV lives in `content/profiles`, one `.json` file each. These are
your personal CV files. They are loaded automatically next time and are
deliberately not sent to GitHub. To make a backup, copy the whole `content`
folder to OneDrive, a USB stick, or another safe place.

To remove a CV, click **Delete this CV**, or delete its file from the folder.
The next start uses the safe example CV again if nothing else is left.

## If you only see “Code → Download ZIP”

That also works. Download it, extract it, and follow the same steps above. A
release ZIP is simply a tidier, ready-to-use version of the same little app.
