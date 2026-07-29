# Make and save your CV

This little app runs on your own computer. Your CV is not uploaded anywhere.

## The first time on Windows

1. Download and unzip the app folder from GitHub.
2. Install **Python 3** from [python.org](https://www.python.org/downloads/). During installation, tick **Add Python to PATH** if you see that choice.
3. Open the unzipped folder and double-click `start-windows.bat`.
4. Your web browser should open the editor. If it does not, open this address yourself: `http://127.0.0.1:8765`.

The first start may take a few minutes because Windows installs the optional
PDF helper. Leave the black window open while using the editor. When you are
finished, close that window.

## Editing your CV

1. Choose a style at the top: **Classic two-column** is compact; **Modern
   single-column** matches the usual published CV style.
2. Replace the example text in “About you”, “Contact details”, and the cards
   below. Add achievements one per line.
3. Use **Move up** and **Move down** to choose the section order. Tick **Start
   this section on a new page** if you want a deliberate page break.
4. The page at the right updates as you type. Click **Save changes** often.
5. Use **Download PDF** when ready. If it says the PDF helper is unavailable,
   download HTML instead, open it in your browser, and choose Print → Save as PDF.

## Where your work is saved

After the first save, the app creates `content/cv.local.json`. This is your
personal CV file. It is automatically loaded next time and is deliberately not
sent to GitHub. To make a backup, copy that one file to OneDrive, a USB stick,
or another safe place.

If you want to start over, close the app and rename or delete
`content/cv.local.json`. The next start uses the safe example CV again.
