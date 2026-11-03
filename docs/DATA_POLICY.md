# Data policy

The corpus defines what the Tribunal can say, so it is curated on purpose. Every law lives in
`data/laws/<theme>/<book>/`, and every book's `source.toml` states its license.

## Themes

- **ancient**: real legal codes, quoted word for word from public-domain translations, or
  paraphrased in our own words in a book with `verbatim = false`.
- **history**: real laws from 1217 to 1959 that sound absurd today, paraphrased from the
  statutes, proclamations and edicts, with each one's date and section.
- **mythology**: rules and punishments from myth, quoted from public-domain translations.
  Stay with traditions that aren't widely practiced religions today (Greek, Norse, Egyptian,
  Mesopotamian), and leave the scriptures and sacred figures of living religions out.
- **fiction**: laws from novels, films and series.
  - Public-domain works (for example *Alice's Adventures in Wonderland*, *Gulliver's Travels*,
    *Erewhon*) may be quoted word for word.
  - Modern, copyrighted works are **paraphrased in our own words**: one or two sentences per
    law, `verbatim = false` in the book's source.toml, and a citation (book and chapter, or series and episode). Never
    paste dialogue, scripts or book text.

## Left out entirely

The laws of regimes such as Nazi Germany or wartime Imperial Japan. This court turns every law
it cites into a joke, and those laws were instruments of persecution and war; even the petty
ones, such as the Nazi ban on jazz, served that machinery.

## Marked sensitive, and never retrieved

Laws about sexual acts, marriage and family, children, enslaved people or self-harm; laws whose
penalty depends on caste, gender or religion; anything about the sacred figures of a religion
practiced today. A comedy app has no business joking about them.

## Sources in use

- ancient/hammurabi: Code of Hammurabi, trans. L. W. King (died 1919). Public domain.
- ancient/salic: The Salic Law, trans. E. F. Henderson (1896; died 1928). Public domain.
- ancient/plutarch-solon: Plutarch, Life of Solon, trans. B. Perrin (1914; died 1920). Public domain.
- ancient/twelve-tables: The Twelve Tables, trans. O. J. Thatcher (1901), in the modernized version
  of Fordham's Internet History Sourcebooks, which allows non-commercial educational use with
  credit. Not used: the Avalon Project's Twelve Tables, a 1961 translation still in copyright.
- mythology/theogony: Hesiod, Theogony, trans. H. G. Evelyn-White (1914; died 1924).
- mythology/metamorphoses: Ovid, Metamorphoses, trans. Brookes More (1922; died 1942).
- fiction/wonderland and fiction/erewhon: published 1865 and 1872. Public domain.
- Every copyrighted story, from fiction/game-of-thrones and fiction/narnia to the Pixar and
  Disney films: paraphrased, nothing quoted.
- Every other book with `verbatim = false`: our own paraphrases of the public-domain sources
  named in its source.toml. DATASET.md lists them all.

If the project ever becomes commercial, replace the Fordham text, and check the trademark and
fan-content policies of any franchise you paraphrase.
