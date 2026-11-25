"""Single source of truth: narration, visuals, AI prompts, callouts, motion, pauses.
make_script.py and build_video.py both import BEATS from here."""

STYLE = ("Cinematic 16:9 documentary still, painterly historical-illustration look, muted sepia and navy palette, "
         "no readable text or lettering, no modern logos, no recognizable real-person faces.")

BEATS = []


def B(sec, narr, vis, prompt, callout="", motion="in", pause=0.6):
    BEATS.append(dict(sec=sec, narr=narr, vis=vis, prompt=prompt, callout=callout, motion=motion, pause=pause))


# ---------------------------------------------------------------- PROLOGUE
S = "Prologue"
B(S, "Hello everyone and I wish you all a very good day.",
  "Slow push-in on an antique world globe in lamplight; Britain is lit gently from within.",
  "Antique brass globe on a oak desk in warm lamplight, Great Britain softly glowing, old maps and a quill beside it.",
  "", "in", 0.4)
B(S, "Hi, my name is Glenn and I welcome you to another interesting story: England's conquest and the rise of the British Empire.",
  "Globe dissolves into a flat world map; the title appears over it. Slow drift left.",
  "Aged parchment world map, 19th-century engraving style, ocean routes faintly inked, empty central space for a title.",
  "ENGLAND'S CONQUEST AND THE RISE OF THE BRITISH EMPIRE", "left", 0.8)
B(S, "At its peak, in the early twentieth century, this one island nation ruled roughly a quarter of the world's land and people. And yet, it was not even the first European empire.",
  "Map of the world with British territories filling in red/pink across Asia, Africa, the Americas, the Pacific and the Caribbean, region by region as each is named.",
  "Early-20th-century style world map with British territories shaded in pink-red on cream paper, subtle vignette, Britain highlighted.",
  "c. 1920 - THE EMPIRE AT ITS PEAK", "out", 1.0)

# ---------------------------------------------------------------- LATE EMPIRE
S = "Britain Arrives Late"
B(S, "Portugal sailed the Atlantic and Indian Oceans first. Spain, after 1492, built a vast American empire on silver mining, plantations, and forced labor.",
  "Map: Portuguese route lines round Africa to India, then Spanish arrows crossing to the Caribbean and Mexico/Peru; cut to an engraving of a silver mine at Potosi.",
  "16th-century engraving of Spanish silver mine in the Andes, workers and tunnels, with a caravel on a distant coast.",
  "PORTUGAL - SPAIN - 1492", "right")
B(S, "Britain arrived late. But it learned from these rivals, competed with them, and eventually surpassed them.",
  "A horizontal timeline: Portugal and Spain bars start early (1400s), Britain's bar begins later (1600s) and grows longest. Parchment background.",
  "Parchment-textured background with three ink-brush horizontal bars of different lengths and starting points, no text.",
  "1400s PORTUGAL / SPAIN  ...  1600s ENGLAND", "in")
B(S, "In 1606, King James the First granted charters to the London Company and the Plymouth Company, letting English investors plant settlements in North America.",
  "Close-up of a charter parchment with a wax royal seal and the date 1606 in the callout; then the Atlantic coast of North America with two shaded zones for the London and Plymouth companies.",
  "Close-up of a royal charter on parchment with a red wax seal and quill, candlelight, early 17th-century style.",
  "1606 - VIRGINIA CHARTERS", "in")
B(S, "In 1607, Jamestown in Virginia became one of the first permanent English settlements in the Americas.",
  "Map zooms to Chesapeake Bay with a marker on Jamestown and the year 1607; dissolve to a triangular palisaded fort on a river.",
  "Triangular wooden palisaded fort beside a wide river, tents inside, small ships moored, early 17th-century illustration.",
  "1607 - JAMESTOWN, VIRGINIA", "in")
B(S, "The Royal Navy was the empire's backbone. It guarded merchant ships, secured sea lanes, defeated rivals, and carried British force across every ocean.",
  "Fleet of ships of the line under full sail; overlay animated sea-lane lines spreading across a world map.",
  "Line of British ships of the line under full sail on a stormy sea, dramatic clouds, painterly 18th-century naval style.",
  "THE ROYAL NAVY", "right")
B(S, "Behind the ships stood money: banks, insurance, credit, and joint-stock companies, which let investors share the risk of voyages lasting years.",
  "A 17th-century London coffee-house of merchants at tables with ledgers; cut-in of a share certificate and an insurance policy for a ship.",
  "Interior of a 17th-century London coffee-house, merchants with ledgers and ship models, warm candlelight.",
  "BANKING - INSURANCE - JOINT-STOCK COMPANIES", "in")
B(S, "Then came the Industrial Revolution. Factories hungry for cotton, rubber, and tin turned colonies into suppliers, and into markets for British goods.",
  "Smoking mill chimneys of a northern English town; animated arrows: raw materials from the colonies into Britain, manufactured goods back out.",
  "Industrial 19th-century English cotton town skyline, smoking chimneys, canal with barges loaded with cotton bales.",
  "RAW MATERIALS IN - MANUFACTURES OUT", "left")
B(S, "That loop made empire profitable for Britain, but it often held back industrial development in the societies it ruled.",
  "Split screen: busy British factory on the left; on the right a quiet colonial port loading raw cotton onto a ship.",
  "Split composition: crowded steam-powered factory floor on one side, colonial harbor with workers loading raw bales on the other.",
  "PROFIT FOR BRITAIN - LIMITED INDUSTRY ABROAD", "in", 1.2)

# ---------------------------------------------------------------- METHODS
S = "Methods of Control"
B(S, "Britain ruled in several ways. In North America and Australia, settlers built permanent colonies and displaced Indigenous peoples.",
  "Map with North America and Australia shaded in one color, labeled 'settler colonies'; small settlement icons spread inward.",
  "19th-century wagon-and-cabin frontier settlement spreading across open land, small figures, wide landscape.",
  "SETTLER COLONIES", "right")
B(S, "In India and Malaya, it often ruled indirectly, through local rulers, traditional elites, and appointed officials.",
  "Map with India and Malaya in a second color labeled 'indirect rule'; illustration of a British official seated beside a local ruler.",
  "A British colonial official seated beside a South Asian prince in an ornate durbar hall, courtiers behind, formal composition.",
  "INDIRECT RULE", "in")
B(S, "And treaties, often signed under military pressure, could transfer territory, open ports, and grant special rights: domination written as diplomacy.",
  "A treaty on a table, a pen hovering; through the window behind, a warship at anchor. Slow push-in.",
  "Treaty document on a polished table with a pen, through the window a large warship with gun ports visible, tense mood.",
  "TREATIES UNDER PRESSURE", "in", 1.0)

# ---------------------------------------------------------------- INDIA
S = "India"
B(S, "Our first case is India. The East India Company arrived in the early seventeenth century as a trading firm, seeking textiles, spices, and indigo, with permission from Mughal rulers.",
  "Map of India with Surat, Madras, Bombay and Calcutta pinned; then a Mughal-style miniature of a European trader presenting goods at court.",
  "Mughal-style miniature painting of a European merchant presenting gifts to an emperor, bales of cloth and indigo in foreground.",
  "EARLY 1600s - EAST INDIA COMPANY ARRIVES", "right")
B(S, "Over time, the Company gained an army, collected taxes, made treaties, and governed territory. A trading firm had become a state.",
  "Rows of Company sepoy infantry drilling; a Company seal and flag; map of Company territory growing.",
  "Rows of sepoy soldiers in red coats drilling in a fort courtyard, Company flag overhead, 18th-century India.",
  "A COMPANY WITH AN ARMY", "in")
B(S, "In June 1757, at the Battle of Plassey, Company forces under Robert Clive defeated Siraj-ud-Daulah, the Nawab of Bengal, helped by the betrayal of key Bengali commanders.",
  "Annotated map of Bengal: Plassey marked with the year 1757; two opposing army blocks with arrows, one of the Nawab's blocks turning away.",
  "Battlefield near a mango grove with two armies, cannon smoke, elephants and infantry, late-afternoon haze, 1757 India.",
  "1757 - BATTLE OF PLASSEY", "in", 1.0)
B(S, "Plassey did not make Britain master of India overnight, but it gave the Company decisive influence in Bengal.",
  "Map of Bengal shading from neutral to Company-colored around Calcutta, spreading slowly.",
  "Aerial-style antique map of the Ganges delta with ink wash spreading from a river port, subtle compass rose.",
  "BENGAL - COMPANY INFLUENCE", "out")
B(S, "In 1764, at the Battle of Buxar, the Company defeated a coalition of Indian forces.",
  "Map: Buxar marked on the Ganges in Bihar with year 1764; three allied armies converge against a single Company force.",
  "Large river-plain battle with several allied Indian armies and a disciplined British line, cannons, banners, 1764.",
  "1764 - BATTLE OF BUXAR", "right")
B(S, "In 1765, the Treaty of Allahabad granted the Company the diwani: the right to collect revenue in Bengal, Bihar, and Orissa.",
  "Close-up of the Treaty of Allahabad document with the callout 'DIWANI'; then a map highlighting Bengal, Bihar and Orissa.",
  "Close-up of a Persian-script and English treaty document with seals, tied ribbons, on a carved wooden table.",
  "1765 - TREATY OF ALLAHABAD", "in", 1.2)
B(S, "Now a company could tax millions of people. That revenue paid its soldiers, bought goods for export, and financed still more conquest.",
  "Animated flow diagram: peasants and merchants -> Company treasury -> soldiers / export goods / new campaigns, looping.",
  "Peasants delivering grain to a tax collector's tent with a Company clerk recording in a ledger, 18th-century Bengal.",
  "REVENUE - ARMY - CONQUEST", "left", 1.0)
B(S, "Parliament noticed. The Regulating Act of 1773 and Pitt's India Act of 1784 brought the Company under growing government control.",
  "Title-page close-ups of each act with dates; cut to the Houses of Parliament exterior at dusk.",
  "18th-century Parliament chamber with members debating, candles, high gallery, dramatic light.",
  "1773 REGULATING ACT - 1784 PITT'S INDIA ACT", "in")
B(S, "After the Rebellion of 1857, the Government of India Act and Queen Victoria's Proclamation of 1858 moved power from the Company to the Crown.",
  "Map pinning Meerut, Delhi, Kanpur and Lucknow (1857); then the 1858 proclamation document and the Allahabad location marked.",
  "Smoke over a north Indian city in 1857, fort walls and soldiers in the distance, somber tones, no graphic violence.",
  "1857 REBELLION - 1858 CROWN RULE", "in", 1.2)
B(S, "The British Raj followed: a Viceroy, the Indian Civil Service, and direct rule, which lasted until independence in 1947.",
  "A Viceroy's procession on elephants and Government House in Calcutta; a banner timeline 1858 to 1947.",
  "Viceregal procession with elephants and honor guard before a large neoclassical government house, 1880s India.",
  "THE RAJ: 1858 - 1947", "right")
B(S, "Railways, telegraphs, and ports spread across India, but largely to serve imperial trade and military needs. Farmers were pushed toward cotton, indigo, and opium.",
  "Railway map of India converging on ports; photographs-style shots of a steam train and telegraph lines; cash-crop fields.",
  "Steam locomotive crossing a large iron bridge in 19th-century India, telegraph poles, fields of cotton and poppy.",
  "RAILWAYS TO PORTS - CASH CROPS", "left")
B(S, "Meanwhile, cheap British factory textiles competed with Indian handloom weavers, bringing hardship to many regions.",
  "Hand-loom weaver at work, then a stack of machine-made cloth bales arriving at an Indian port.",
  "Indian weaver at a wooden handloom in a village workshop, handwoven cloth, contrasted with machine-made bales at the dock.",
  "HANDLOOMS VS FACTORY CLOTH", "in", 1.4)

# ---------------------------------------------------------------- CHINA
S = "China"
B(S, "China was never colonized in the same way. It stayed formally independent under the Qing dynasty, but Britain used war and treaties to pry open its markets.",
  "Map of Qing China with the coast highlighted; a Qing-era painting of the Canton waterfront with foreign trading houses.",
  "Qing-era painting-style view of the Canton waterfront, foreign trading houses with flags, junks and river traffic.",
  "QING CHINA - CANTON", "right")
B(S, "The issue was opium. Merchants shipped opium grown in British India to China, fueling addiction and a deep social and economic crisis.",
  "Animated arrows from Bengal to Canton on a map; cut to sealed opium chests stacked in a warehouse and a ledger page.",
  "Stacked wooden chests in a dim warehouse, a clerk with a ledger, a ship loading in the background, somber tone.",
  "BRITISH INDIA - OPIUM - CHINA", "left", 1.2)
B(S, "When the Qing tried to stop the trade, Britain answered with force. The First Opium War ran from 1839 to 1842.",
  "Map of the Chinese coast with 1839-1842 date bar; British steam warships entering the Pearl River.",
  "British steam-powered warship firing broadside at Chinese coastal fortifications at dawn, smoke and junks, 1841.",
  "1839-1842 - FIRST OPIUM WAR", "in")
B(S, "Britain's navy attacked coastal cities and controlled key waterways. On August 29, 1842, the Treaty of Nanjing was signed aboard a British warship.",
  "Map highlighting Nanjing on the Yangtze with the date; then a signing scene aboard HMS Cornwallis.",
  "Treaty signing in a ship's cabin, British naval officers and Qing officials around a table, 1842, formal composition.",
  "29 AUGUST 1842 - TREATY OF NANJING", "in", 1.2)
B(S, "China ceded Hong Kong Island, opened five ports to foreign trade, and paid a large indemnity. This began the era of the unequal treaties.",
  "Map: Hong Kong Island circled, five ports pinned (Canton, Amoy, Foochow, Ningpo, Shanghai); coins stacking for the indemnity.",
  "Antique chart of the South China coast with a harbor island circled in red ink and five ports marked with small pins.",
  "HONG KONG CEDED - FIVE TREATY PORTS", "out")
B(S, "More followed: the Treaty of the Bogue in 1843, the Treaty of Tianjin in 1858, and the Convention of Peking in 1860, which ceded Kowloon.",
  "Three document close-ups appear in sequence with dates; map adds Tianjin, Peking and the Kowloon peninsula.",
  "Three aged treaty pages fanned on a desk with Chinese and English text blocks and seals, soft shadows.",
  "1843 BOGUE - 1858 TIANJIN - 1860 PEKING", "right")
B(S, "Hong Kong became a major British port and financial center, governed by Britain until 1997.",
  "Day-to-night timelapse-style view of Victoria Harbour with ships; callout 1997.",
  "Late-19th-century Victoria Harbour, Hong Kong, steamships, warehouses and hillside buildings under golden light.",
  "HONG KONG: BRITISH UNTIL 1997", "out")

# ---------------------------------------------------------------- AMERICAS
S = "The Americas"
B(S, "Back across the Atlantic, British settlement spread from Virginia to New England, the Caribbean, and later Canada. The Mayflower Compact of 1620 sketched a framework for self-government among Plymouth's settlers.",
  "Map with Virginia, New England, Caribbean islands and Canada lighting in turn; then the Mayflower Compact document, 1620.",
  "Small wooden ship approaching a rocky New England shore in cold light, passengers on deck, 1620 style.",
  "1620 - MAYFLOWER COMPACT", "right")
B(S, "For Indigenous nations, the consequences were severe: disease, warfare, land seizure, and displacement from lands they had inhabited for thousands of years.",
  "Slow, respectful pan across a river valley village at dawn; map shows Indigenous territories shrinking as colonial lines advance.",
  "Indigenous village with longhouses by a river at dawn, smoke rising, people at daily life, quiet respectful composition.",
  "INDIGENOUS LANDS LOST", "in", 1.6)
B(S, "The empire also became deeply tied to the transatlantic slave trade. Enslaved Africans were transported to work sugar, tobacco, and cotton plantations.",
  "Map of the triangular trade (Britain - West Africa - Caribbean/North America) with moving lines; archival engraving of a plantation landscape. Show no graphic imagery.",
  "Archival engraving-style Caribbean sugar plantation landscape with distant fields and a windmill, restrained somber tone.",
  "TRANSATLANTIC SLAVE TRADE", "left", 1.6)
B(S, "It generated enormous profit for British merchants, planters, and financial institutions, at immense human cost.",
  "A merchant's ledger page and a port-city counting-house; slow push-in on the ledger.",
  "Close-up of an 18th-century merchant ledger with columns of handwritten entries beside a ship model, candlelit.",
  "PROFIT AND HUMAN COST", "in", 1.8)
B(S, "The Royal Proclamation of 1763 reserved lands west of the Appalachians for Indigenous peoples. In practice, settlers and speculators often ignored it.",
  "Map: Appalachian line drawn and the region west of it shaded; then arrows of settlers crossing the line.",
  "Antique map of eastern North America with a bold ink line along the Appalachians and a shaded western region.",
  "1763 - ROYAL PROCLAMATION", "right")
B(S, "Britain abolished its slave trade in 1807, and slavery in most colonies in 1833, though with years of forced 'apprenticeship'. A major moral achievement, after centuries of profit.",
  "Documents appear: Abolition of the Slave Trade Act 1807, Slavery Abolition Act 1833; a timeline bar 1807 - 1833 - apprenticeship years.",
  "Parliamentary act pages with ribbons beside broken chain links on a dark table, solemn lighting.",
  "1807 TRADE ABOLISHED - 1833 SLAVERY ABOLISHED", "in", 1.6)

# ---------------------------------------------------------------- AUSTRALIA
S = "Australia"
B(S, "Captain James Cook charted Australia's east coast in 1770. In 1788, the First Fleet reached Port Jackson and founded a penal colony near present-day Sydney.",
  "Map of the east coast with Cook's 1770 route; then Port Jackson marked 1788, eleven ships arriving in the harbor.",
  "Eleven sailing ships entering a natural harbor with sandstone headlands, 1788, early morning light.",
  "1770 COOK - 1788 FIRST FLEET, PORT JACKSON", "right")
B(S, "British authorities treated the land as terra nullius, 'land belonging to no one', denying the sovereignty of Aboriginal and Torres Strait Islander peoples and bypassing any treaty.",
  "Map of Australia with many Aboriginal nations' territories faintly outlined, then overlaid by British colony boundaries; the phrase 'terra nullius' appears as a callout.",
  "Aerial-style map of Australia with faint mosaic of territories under an overlay of straight colonial boundary lines.",
  "TERRA NULLIUS", "in", 1.4)
B(S, "The effects were devastating: loss of land, water, and sacred sites, disease, violence, massacres, and forced removals. Their consequences endure today.",
  "Quiet landscape of country at dusk with a waterhole and ancient rock art, held for a still moment. No depiction of violence.",
  "Australian landscape at dusk with a waterhole and an ochre rock-art wall, calm and reverent, no figures.",
  "LAND - WATER - SACRED SITES", "in", 2.0)
B(S, "Wool, farming, and mining built a settler economy, while Indigenous peoples were shut out of political power.",
  "Sheep station and a gold-rush mine; the final frame leaves empty a parliament-chair icon.",
  "Vast Australian sheep station at sunrise with shearing shed, then a goldfield with tents, painterly style.",
  "WOOL - FARMING - MINING", "left")

# ---------------------------------------------------------------- NEW ZEALAND
S = "New Zealand"
B(S, "New Zealand took a different path. Cook charted its coast in 1769 and 1770, and missionaries, traders, and settlers followed.",
  "Map of two main islands with Cook's route and dates; cut to a mission station and a trading ship at a bay.",
  "Bay in New Zealand with a small mission station, a trading ship at anchor and a Māori waka nearby, 1830s.",
  "1769-1770 COOK CHARTS NEW ZEALAND", "right")
B(S, "In 1840, the Crown and many Māori chiefs signed the Treaty of Waitangi. But the English and Māori versions differed on sovereignty and authority.",
  "Close-up of the Treaty of Waitangi document; two side-by-side text columns ('English' / 'Māori') with a highlighted difference; Waitangi marked on the map.",
  "Large marquee on a green lawn by a bay, British officials and Māori chiefs gathered, signing table, 1840.",
  "1840 - TREATY OF WAITANGI", "in", 1.2)
B(S, "Disputes over land led to the New Zealand Wars, and Māori lost vast territories. In 1975, the Waitangi Tribunal was created to hear their grievances.",
  "Map of North Island land holdings shifting from Māori to Crown/settler shading; then a hearing room, 1975.",
  "Rolling North Island hills with a Māori meeting house and distant surveyors' stakes, evening light.",
  "NEW ZEALAND WARS - 1975 WAITANGI TRIBUNAL", "out", 1.0)

# ---------------------------------------------------------------- MALAYA
S = "Malaya"
B(S, "In Malaya, Britain ruled indirectly. The Pangkor Treaty of 1874 placed a British Resident beside the Sultan of Perak, leaving religion and Malay custom to local authorities.",
  "Map of the Malay Peninsula with Perak marked and the year 1874; scene of a Resident and a Sultan seated together signing.",
  "Interior of a Malay palace hall, a British official and a Sultan in traditional dress seated side by side with a document.",
  "1874 - PANGKOR TREATY, PERAK", "in", 1.0)
B(S, "The Residents gradually gained control of finance and administration, and the Federated Malay States of 1895 centralized the colonial structure.",
  "Map: Perak, Selangor, Negeri Sembilan and Pahang merge into one shaded federation; document close-up dated 1895.",
  "Neoclassical colonial administration building in Kuala Lumpur with clerks and officials on the verandah, 1890s.",
  "1895 - FEDERATED MALAY STATES", "right")
B(S, "Tin mines and rubber plantations drove exports, with Singapore as the commercial hub. Chinese and Indian labor migration reshaped society, and created lasting divisions.",
  "Tin mine pit with workers, rows of rubber trees being tapped, then a Singapore harbor of ships; migration arrows from China and India.",
  "Rows of rubber trees with tappers at dawn, a tin-mining pit in the distance, Singapore harbor sketch in the corner.",
  "TIN - RUBBER - SINGAPORE", "left", 1.0)

# ---------------------------------------------------------------- ECONOMY
S = "Economy"
B(S, "Across the empire, cotton, tea, sugar, rubber, tin, opium, and manufactured goods moved along a vast network, enriching British ports, banks, insurers, and shippers.",
  "World map with glowing trade lanes and commodity icons per region; zoom into London docks.",
  "London docks crowded with cargo ships, crates marked with commodity symbols, cranes and warehouses, dusk.",
  "THE IMPERIAL TRADING NETWORK", "right")
B(S, "Joint-stock companies, banks, and commercial law spread worldwide. But colonial economies were largely organized to serve British industry, not local development.",
  "Summary table animates in: Region / British interest / Long-term effect for India, China, Americas, Australia, Malaya, one row per region.",
  "Clean parchment infographic background with five horizontal bands, each with a small motif: loom, tea chest, plantation, wool bale, tin ingot.",
  "WHO BENEFITED?", "in", 1.4)

# ---------------------------------------------------------------- CULTURE
S = "Culture & Education"
B(S, "The English language spread through administration, commerce, schools, law, and print, becoming a major language of diplomacy, science, and business.",
  "Printing press, a colonial schoolroom, and a map with English spreading outward as a color wash.",
  "Colonial schoolroom with students at wooden desks, a blackboard and a teacher, tropical light through shutters.",
  "THE SPREAD OF ENGLISH", "in")
B(S, "Colonial schools trained clerks, lawyers, and teachers, and some of those graduates used the ideas of rights and self-government to challenge British rule.",
  "Young lawyer in a courtroom and a crowd meeting under a banner; slow pan.",
  "Young colonial-era lawyer in a dark gown addressing a packed courtroom, law books, ceiling fans.",
  "EDUCATION AND ANTI-COLONIALISM", "right")
B(S, "Culture flowed both ways. Colonized peoples adapted British institutions into new political movements, literatures, and national identities.",
  "Montage of a newspaper press, a poet reading, a political meeting.",
  "Busy 1920s print shop in a colonial city, hand-set type, newspapers drying, staff at work.",
  "ADAPTATION AND NEW IDENTITIES", "in")

# ---------------------------------------------------------------- RESISTANCE
S = "Resistance & Decolonization"
B(S, "Resistance never stopped: the 1857 rebellion in India, Indigenous war and diplomacy in the Americas, Aboriginal resistance in Australia, Māori challenges in New Zealand, and nationalists in Malaya.",
  "Five map flashes, each with its region and date lit in turn: India 1857, Americas, Australia, New Zealand, Malaya.",
  "Five-panel painterly triptych: village defenders, delegation at council fire, stockade gate, hilltop pā, nationalist rally.",
  "RESISTANCE ACROSS THE EMPIRE", "out", 1.0)
B(S, "After World War Two, a weakened Britain faced stronger nationalist movements. In 1947, India and Pakistan became independent.",
  "Map of South Asia with the partition boundaries appearing and the date; crowd celebrating at midnight.",
  "Crowd gathered at a government building at midnight, flags being raised, lamps and joyful faces from behind, 1947.",
  "1947 - INDIA AND PAKISTAN INDEPENDENT", "in", 1.2)
B(S, "Many former colonies joined the Commonwealth. In 1997, Hong Kong returned to China, often seen as the symbolic end of Britain's territorial empire.",
  "Commonwealth flag-lights across a map, then Hong Kong harbor with the date 1 July 1997 on a lowered flag.",
  "Hong Kong harbor at night with a flag being lowered on a ceremony stage and fireworks reflected on water.",
  "1997 - HONG KONG RETURNED", "in", 1.2)

# ---------------------------------------------------------------- BRITAIN TODAY
S = "Britain Today"
B(S, "Britain still shapes the world through the Commonwealth, the English language, London's financial markets, its universities, and its cultural exports.",
  "Modern London skyline with the Thames at dusk, university quads, a book-and-screen montage.",
  "Contemporary London skyline across the Thames at blue hour, financial towers and old stone bridges.",
  "BRITAIN TODAY", "out")
B(S, "And debates over reparations, racism, Indigenous land rights, migration, and how to remember empire continue in Britain and in its former colonies.",
  "Statues and museum displays; people reading a plaque; slow dolly through a museum gallery.",
  "Museum gallery with visitors reading interpretive panels beside colonial-era artifacts, soft daylight.",
  "A CONTESTED LEGACY", "in", 1.4)

# ---------------------------------------------------------------- CONCLUSION
S = "Conclusion"
B(S, "Britain came late. Yet it succeeded by combining commerce, naval strength, finance, industry, and political organization.",
  "Five icons assemble on parchment: ship, coin, ledger, factory, parliament.",
  "Five symbols on aged parchment: ship, coin, ledger, chimney, parliament dome, inked in sepia.",
  "COMMERCE - NAVY - FINANCE - INDUSTRY - POLITICS", "in")
B(S, "Its empire brought trade and institutions, and also conquest, exploitation, and dispossession. It cannot be told only as progress.",
  "Two-panel slow cross-fade: bustling trade harbor to empty dispossessed landscape.",
  "Two halves: bustling colonial harbor with ships on one side, empty farmland with abandoned huts on the other.",
  "PROGRESS AND DISPOSSESSION", "in", 1.4)
B(S, "It is a story of power, resistance, and inequality, and understanding it helps explain the world we live in. Thank you for watching.",
  "Slow pull-out from the globe in lamplight; map goes dark except a faint light across former colonies. Fade to black.",
  "Antique globe in lamplight, camera pulling back, lamp dimming, long shadows, quiet ending.",
  "THANK YOU FOR WATCHING", "out", 2.0)

# ---------------------------------------------------------------- AUDIO PER SECTION
SECTION_AUDIO = {
    "Prologue": ("Warm, welcoming, curious; then measured and authoritative.", "Soft ambient strings with a slow pulse; low sea-wind bed.", ""),
    "Britain Arrives Late": ("Analytical, brisk; slightly grander on the Navy.", "Light baroque harpsichord/lute, rising brass swell on the Royal Navy beat; creaking ship ambience.", ""),
    "Methods of Control": ("Cool, explanatory; darker on 'domination written as diplomacy'.", "Minimal drone; faint wax-seal and pen-scratch foley.", ""),
    "India": ("Narrative momentum; grave at Plassey and 1857; matter-of-fact on laws.", "Tanpura drone and sitar motifs; low drums at Plassey/Buxar; railway chug under the railway beat.", ""),
    "China": ("Measured, serious; slow and heavy on the opium and unequal treaties.", "Guzheng and low strings; distant cannon only at the First Opium War beat; harbor ambience.", ""),
    "The Americas": ("Reflective; slowest and quietest on Indigenous loss and slavery; resolve on abolition.", "Sparse piano and cello; no percussion on slavery beats; pure room-tone pause after the ledger line.", ""),
    "Australia": ("Sober and respectful; long silences.", "Didgeridoo-free (avoid appropriating): ambient wind, birdsong, soft low strings.", ""),
    "New Zealand": ("Measured, thoughtful; emphasize the translation difference.", "Gentle taonga pūoro-inspired textures only if licensed from Māori artists; otherwise soft ambient.", ""),
    "Malaya": ("Informative, steady.", "Light gamelan-adjacent percussion or neutral ambient; rain and jungle ambience.", ""),
    "Economy": ("Crisp, analytical, slightly faster.", "Pulsing minimal electronic/strings bed; ticking clock.", ""),
    "Culture & Education": ("Warmer, hopeful.", "Piano with gentle strings; schoolroom murmur.", ""),
    "Resistance & Decolonization": ("Rising energy, then triumphant but restrained at 1947.", "Building strings and drums; a short silence before 1947.", ""),
    "Britain Today": ("Contemplative, level.", "Soft modern ambient pads; city murmur.", ""),
    "Conclusion": ("Slow, balanced, reflective; final line unhurried.", "Return of the opening theme, thinning to a single sustained note.", ""),
}
