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

## Editing your CV

1. Choose a style at the top: **Classic two-column** is compact; **Modern
   single-column** matches the usual published CV style.
2. At the top, choose a **CV profile** to switch between saved CVs. Click
   **New profile** to create a separate copy for a different person or job type.
3. Replace the example text in “About you”, “Contact details”, and the cards
   below. Add achievements one per line.
4. Use **Move up** and **Move down** to choose the section order. Tick **Start
   this section on a new page** if you want a deliberate page break.
5. The page at the right updates as you type. Click **Save changes** often.
6. When ready, use your browser’s Print command (usually `Ctrl` + `P`) and
   choose **Save as PDF**. This is the normal Windows way to make your PDF.
   The **Download PDF** button is optional and only works when the extra PDF
   helper has already been installed.

## Where your work is saved

After the first save, the app creates `content/cv.local.json`. Extra profiles
are saved in `content/profiles`. These are your personal CV files. They are
automatically loaded next time and are deliberately not sent to GitHub. To make
a backup, copy the whole `content` folder to OneDrive, a USB stick, or another
safe place.

If you want to start over, close the app and rename or delete
`content/cv.local.json`. The next start uses the safe example CV again.

## If you only see “Code → Download ZIP”

That also works. Download it, extract it, and follow the same steps above. A
release ZIP is simply a tidier, ready-to-use version of the same little app.
