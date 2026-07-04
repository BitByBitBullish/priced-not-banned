THE FIGHT, IN ONE MINUTE
- Core wants: don't judge transactions. If it pays the fee and follows the rules,
 it gets in. Filters are censorship, and they don't work anyway.
- Knots wants: Bitcoin is money, not a hard drive. Spam (jpegs, files) floods
 blocks at a 75% discount, raising fees and burdening node runners.
- Both are right about something. That's why neither side can win this.

MY SUGGESTION (two parts)
1. Keep the discount for money, end it for bulk data. Every real money
 transaction ever measured uses under ~700 bytes of signature space. So the
 first 2,000 bytes stay discounted — every wallet, multisig, and Lightning
 transaction changes by exactly zero. Past 2,000 is still allowed, it just
 pays full price. Spam loses its coupon.
2. Give data a proper parking spot. A separate lane where data is stamped and
 provable forever, but nodes don't have to store it. Cheaper for honest data
 users, lighter for every node runner. (Credit where due: this lane builds
 on an earlier concept from Samson Mow — a respected voice on the Knots
 side. The 2,000-byte cap is my contribution; together they meet in the
 middle.)

SO WHO ACTUALLY PAYS MORE? (almost nobody — here are the real numbers)
We measured 439,000+ real transaction inputs, randomly sampled across
Bitcoin's entire modern era (2017 to today), reproducible by anyone:
- A typical transaction uses ~104 bytes. That's 5% of the cap.
- The biggest real multisig we found: a 4-of-5 at 458 bytes — under a
 QUARTER of the cap.
- The biggest money transaction of ANY kind we found: 696 bytes — about
 a third of the cap.
- A 15-of-15 vault (the biggest setup anyone realistically uses): never
 appeared ONCE in our sample — and even if someone used one tomorrow,
 it's 1,608 bytes. Still under the cap. Pays ZERO extra.
- The only standard setup that would ever pay more: a 20-of-20 multisig,
 the absolute maximum Bitcoin's rules allow. It has never appeared once
 in our sample either. If someone someday uses one, it pays about 100
 extra vbytes — typically well under a dollar. Never blocked.
- Now compare that to a picture: an actual jpeg usually runs 20,000 to
 100,000+ bytes — 10 to 50+ times the cap. The image spam we measured
 went past 200,000. Bitcoin's biggest-ever theoretical money transaction
 (1,608 bytes) isn't even a TENTH of a small jpeg. That's the whole
 point: money and pictures live in completely different size worlds,
 so a line at 2,000 never touches money.
Bottom line: not ONE real money transaction we measured — 51,906 of them
in the independent draw — would have paid a single extra sat. The only
things that pay more are the bulk-data/spam transactions. That's not a
side effect; that's the design.

BUT WHAT ABOUT THE GROSS STUFF? (the "no child porn / dick pics on Bitcoin" argument)
First, know what's actually on the chain: there are NO pictures on Bitcoin.
There never were. The chain stores scrambled code (bytes). Nobody scrolling
the blockchain ever sees an image. A picture only exists if a separate
website/app decodes those bytes back into one — and THOSE sites are where
blocking actually works: they can refuse to display flagged content, get
taken down, and face real legal liability. No Bitcoin rule — Core's, Knots',
or anyone's — can read content: encryption makes any file look like random
noise. Anyone promising a protocol filter for bad content is promising
the impossible.
What each side actually does about it:
- Core: nothing. The data flood keeps its 75% discount.
- Knots/BIP-110: filters determined uploaders bypass — and worse, banning
 data at the rule level creates a documented attack where someone embeds
 illegal content ON PURPOSE to force chain chaos (BitMEX flagged this:
 the ban hands criminals a weapon).
- Mine: kills the discount so the flood stops being cheap, and moves data
 into a lane nodes never have to store — node runners are no longer forced
 to host anyone's garbage. Less of it, nobody has to keep it, and the sites
 that make it viewable stay legally accountable.

WHY BOTH SIDES GET WHAT THEY WANT
- Core gets: no censorship (the rule counts bytes, never reads content),
 nothing banned, no coins frozen, nothing breaks.
- Knots gets: the spam subsidy dead, bulk data paying real costs, and node
 runners never forced to store jpegs again.

WHY NONE OF BIP-110'S PROBLEMS
- Frozen coins: BIP-110's own critics documented rare cases where its bans
 could make some existing coins UNSPENDABLE — frozen forever. Mine
 mathematically can't: nothing ever becomes invalid, so no coin can ever
 be stranded. Worst case anywhere in my design: see the rarity numbers
 above — a transaction type nobody has ever used pays under a dollar extra.
- No chain-split gamble — this activates only with overwhelming agreement
 (90%+), or not at all.
- No censorship fight — a 50KB image and a 50KB contract pay identically.
- Honest about limits: nothing fully stops determined spammers. This kills
 their discount and offers data a better home. Prices, not bans.

Backed by measurement, not opinion: 439,000+ real transaction inputs analyzed,
every number reproducible.
