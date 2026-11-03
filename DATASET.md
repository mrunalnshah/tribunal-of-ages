# The expanded law library

234 new paraphrased laws, in 74 new books and in the existing Game of Thrones and
Harry Potter books, on top of the library the guide builds: real ancient codes, a history theme
of real laws from 1217 to 1959 that sound absurd today, mythology, public-domain classics, and
famous books, films, series and cartoons. New laws by theme: ancient 33, fiction 127, history 39, mythology 35.

## Add it to your project

Unzip it into your project folder, letting it replace `data/laws/` and `docs/DATA_POLICY.md`.
Your own laws come along, because the zip holds the whole library. Then label the new laws,
rebuild the index and the library's shelf, and check:

```bash
uv run tribunal curate        # labels the new laws: one AI call per batch, on your Groq quota
uv run tribunal check
uv run tribunal index
uv run tribunal shelve
uv run pytest
```

These are the same in PowerShell. Read `data/review.csv` after curating, as Step 7 shows, and
commit `data/laws/` and `data/processed/` together.

## The eval comes too

The zip also replaces `data/eval/retrieval.jsonl` and `data/eval/verdicts.jsonl`. The verdict eval
gains two cases at outrage 4, your sister's food photos among them, because a furious plaintiff
needs tier-4 laws, and the Qing, Athenian, Roman, Icelandic and Shakespearean banishments are
there to supply them. In the retrieval eval, the guide's cases were written for its
smaller library, so four are corrected: new laws that genuinely answer a grievance now count
(Goldilocks' porridge for the stolen pizza, Solon's law against idleness for the lazy roommate),
and `hammurabi-53` is gone, because curate rightly marks it sensitive and search never returns
it. Twenty-six new cases check that the new laws can be found. CI fails below a Hit@5 of 0.6, so
run `uv run tribunal eval` before you push. Cases whose laws are still `PASTE` placeholders are
skipped, not failed: paste those texts (Step 7) and they count.

## Every law is a paraphrase

Each book says `verbatim = false`, so the court shows these laws as "Paraphrased from", never
as quotations. The texts are short summaries in our own words, each with its citation. For a
public-domain source, you can make a book verbatim: replace each text with the exact passage
from the book's `source_url`, then set `verbatim = true`. Copyrighted stories, from Narnia and
Star Wars to the Pixar films, stay paraphrased for good. The project is non-commercial; if that
ever changes, check each franchise's trademark and fan-content policy.

## Left out on purpose

Laws that the data policy would mark sensitive: about marriage and family, children, sexual
conduct, or with penalties that depend on gender or caste. The curate step would hide them
anyway. And the laws of regimes such as Nazi Germany or wartime Imperial Japan: this court
turns every law it cites into a joke, and those laws were instruments of persecution.

## The books

| Theme | Book | Jurisdiction | Source | Laws |
|---|---|---|---|---|
| ancient | `athenian-constitution` | Athens | Aristotle, The Athenian Constitution, trans. F. G. Kenyon (1891), and Plutarch, Life of Aristides | 2 |
| ancient | `gragas` | The Icelandic Commonwealth | Grágás, the laws of the Icelandic Commonwealth | 2 |
| ancient | `lycurgus` | Sparta | Plutarch, Life of Lycurgus, trans. B. Perrin (1914) | 6 |
| ancient | `qing-code` | Qing China | The Great Qing Code, trans. G. T. Staunton (1810) | 6 |
| ancient | `roman-exile` | Rome | Roman exile, as described by Cicero, Livy and Ovid | 2 |
| ancient | `roman-sumptuary` | Rome | Rome's laws against luxury, as reported by Livy, Macrobius and Aulus Gellius | 4 |
| ancient | `solon` | Athens | Plutarch, Life of Solon, chapters 20-24, trans. B. Perrin (1914) | 11 |
| fiction | `aladdin` | Agrabah | Disney, Aladdin | 2 |
| fiction | `animal-farm` | Animal Farm | George Orwell, Animal Farm | 3 |
| fiction | `asimov-robots` | Asimov's robots | Isaac Asimov, the robot stories | 2 |
| fiction | `avatar` | The Four Nations | Avatar: The Last Airbender | 2 |
| fiction | `back-to-the-future` | Hill Valley | Back to the Future | 1 |
| fiction | `brobdingnag` | Brobdingnag | Jonathan Swift, Gulliver's Travels (1726), part II | 1 |
| fiction | `catch-22` | Pianosa | Joseph Heller, Catch-22 | 1 |
| fiction | `discworld` | Ankh-Morpork | Terry Pratchett, the Discworld novels | 2 |
| fiction | `doctor-who` | Gallifrey | Doctor Who | 2 |
| fiction | `dune` | Arrakis | Frank Herbert, Dune | 4 |
| fiction | `erewhon-retold` | Erewhon | Samuel Butler, Erewhon (1872) | 2 |
| fiction | `fahrenheit-451` | The firemen's city | Ray Bradbury, Fahrenheit 451 | 1 |
| fiction | `fairy-tales` | Once upon a time | Fairy tales by Charles Perrault (1697), Jeanne-Marie Leprince de Beaumont (1756) and Robert Southey (1837) | 3 |
| fiction | `ferengi` | Ferenginar | Star Trek: Deep Space Nine | 4 |
| fiction | `fight-club` | Fight Club | Fight Club | 1 |
| fiction | `finding-nemo` | The reef | Pixar, Finding Nemo | 1 |
| fiction | `foundation` | Terminus | Isaac Asimov, Foundation | 4 |
| fiction | `game-of-thrones` | Westeros | George R. R. Martin, A Game of Thrones | 10 |
| fiction | `ghostbusters` | The Ghostbusters' firehouse | Ghostbusters | 1 |
| fiction | `gremlins` | Kingston Falls | Gremlins | 1 |
| fiction | `harry-potter` | Hogwarts | J. K. Rowling, the Harry Potter novels | 6 |
| fiction | `hitchhikers-guide` | The Galaxy, as the Guide sees it | Douglas Adams, The Hitchhiker's Guide to the Galaxy | 1 |
| fiction | `how-to-train-your-dragon` | Berk | DreamWorks, How to Train Your Dragon | 1 |
| fiction | `hunger-games` | Panem | Suzanne Collins, The Hunger Games trilogy | 5 |
| fiction | `incredibles` | Metroville | Pixar, The Incredibles | 2 |
| fiction | `law-of-the-jungle` | The Jungle | Rudyard Kipling, The Law of the Jungle, in The Second Jungle Book (1895) | 5 |
| fiction | `lilliput` | Lilliput | Jonathan Swift, Gulliver's Travels (1726), part I | 10 |
| fiction | `lion-king` | The Pride Lands | Disney, The Lion King | 1 |
| fiction | `looking-glass` | Looking-Glass Land | Lewis Carroll, Through the Looking-Glass (1871) | 3 |
| fiction | `men-in-black` | The Men in Black | Men in Black | 1 |
| fiction | `middle-earth` | Middle-earth | J. R. R. Tolkien, The Hobbit and The Lord of the Rings | 6 |
| fiction | `mikado` | Titipu | W. S. Gilbert and Arthur Sullivan, The Mikado (1885) | 2 |
| fiction | `moana` | Motunui | Disney, Moana | 1 |
| fiction | `narnia` | Narnia | C. S. Lewis, The Chronicles of Narnia | 8 |
| fiction | `nineteen-eighty-four` | Oceania | George Orwell, Nineteen Eighty-Four | 1 |
| fiction | `oz` | The Emerald City | L. Frank Baum, The Wonderful Wizard of Oz (1900) | 2 |
| fiction | `phantom-tollbooth` | The Doldrums | Norton Juster, The Phantom Tollbooth | 1 |
| fiction | `pinocchio` | Catchfools | Carlo Collodi, The Adventures of Pinocchio (1883) | 1 |
| fiction | `pirates-of-penzance` | Penzance | W. S. Gilbert and Arthur Sullivan, The Pirates of Penzance (1879) | 2 |
| fiction | `pirates-of-the-caribbean` | The Caribbean, under the Pirate Code | Pirates of the Caribbean | 2 |
| fiction | `pokemon` | The Pokémon world | The Pokémon games | 2 |
| fiction | `red-rising` | The Society | Pierce Brown, Red Rising | 2 |
| fiction | `shakespeare` | Shakespeare's courts | William Shakespeare's plays | 3 |
| fiction | `star-trek` | The Federation | Star Trek | 1 |
| fiction | `star-wars` | A galaxy far, far away | The Star Wars films and series | 7 |
| fiction | `toy-story` | Andy's room | Pixar, Toy Story | 1 |
| fiction | `treasure-island` | The Hispaniola | Robert Louis Stevenson, Treasure Island (1883) | 2 |
| fiction | `wall-e` | The Axiom | Pixar, WALL-E | 1 |
| fiction | `wind-in-the-willows` | The county court | Kenneth Grahame, The Wind in the Willows (1908) | 1 |
| fiction | `wreck-it-ralph` | Litwak's Arcade | Disney, Wreck-It Ralph | 1 |
| history | `edo-japan` | Tokugawa Japan | Edicts of the Tokugawa shogunate, 1615-1843 | 4 |
| history | `england` | England | English statutes, proclamations and charters, 1217-1735 | 8 |
| history | `finland` | Finland | Finland's prohibition law of 1919 | 1 |
| history | `iceland` | Iceland | Iceland's prohibition law of 1915 | 1 |
| history | `massachusetts` | Massachusetts Bay Colony | Laws of the Massachusetts Bay Colony | 1 |
| history | `ottoman` | The Ottoman Empire | The decrees of Sultan Murad IV | 1 |
| history | `petrine-russia` | Russia under Peter the Great | Decrees of Peter the Great, 1698-1718 | 3 |
| history | `scotland` | Scotland | Acts of the Parliament of Scotland, 1457 and 1491 | 2 |
| history | `united-states` | The United States | Prohibition and Hollywood's Production Code, 1919-1934 | 3 |
| history | `victorian-streets` | Victorian England | Acts of Parliament, 1824-1872 | 11 |
| history | `wartime-britain` | Britain at war, 1914-1918 | The Defence of the Realm Act and its orders, 1914-1918 | 4 |
| mythology | `book-of-the-dead` | The Hall of Two Truths | The Book of the Dead, chapter 125, trans. E. A. Wallis Budge (1895) | 11 |
| mythology | `greek-myths` | Olympus | Greek myths, retold from Hesiod, Homer, Pindar and Ovid | 9 |
| mythology | `journey-to-the-west` | The Heavenly Court | Wu Cheng'en, Journey to the West (16th century) | 2 |
| mythology | `kojiki` | Yomi, the land of the dead | The Kojiki (712), trans. B. H. Chamberlain (1882) | 1 |
| mythology | `kojiki-heaven` | Takamagahara, the High Plain of Heaven | The Kojiki (712), trans. B. H. Chamberlain (1882) | 1 |
| mythology | `poetic-edda` | Asgard | The Poetic Edda, trans. H. A. Bellows (1923) | 9 |
| mythology | `ulster-cycle` | Ulster | The Ulster Cycle, as told in Lady Gregory's Cuchulain of Muirthemne (1902) | 1 |
| mythology | `urashima` | The Dragon Palace | The Japanese folk tale of Urashima Taro | 1 |
