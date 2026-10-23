# 11 Glossary

Plain-language definitions of the terms used in FlameAtlas and its documents. Owners: Aurin Subah (science terms) and Farhan Alam Chowdhury (wording).

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-24 | First baseline |

## Fire science

| Term | Meaning |
|---|---|
| **Microgravity** | The near-weightless condition in orbit, for example aboard the ISS. Objects and gases do not "fall", so hot air does not rise. Often written μg. |
| **Partial gravity** | Gravity weaker than Earth's but not near zero: about 0.17 g on the Moon and 0.38 g on Mars. |
| **Buoyant convection** | On Earth, hot flame gases are lighter than the surrounding air, so they rise and pull in fresh air. This is why a candle flame is a teardrop. In microgravity it disappears. |
| **Forced flow** | Air moved by a fan or ventilation system rather than by buoyancy. In a spacecraft this is the only way fresh air reaches a flame. |
| **Concurrent flow** | Air moving in the same direction as the flame is spreading. It pushes hot gas ahead of the flame and usually helps it spread. |
| **Opposed flow** | Air moving against the direction the flame is spreading. |
| **Stagnation flow** | Air flowing straight onto the tip of a sample, such as the end of a rod. |
| **Quiescent** | No air movement at all. |
| **Flame spread rate** | How fast the flame front moves along a material, in mm/s. |
| **Ignition** | The moment a material starts burning on its own after the igniter heats it. **No ignition** means the igniter ran but no lasting flame formed. |
| **Self-extinguish** | A flame that goes out by itself, without a fire extinguisher, before the material is used up. |
| **Quenching extinction** | A flame going out because too little fresh oxygen reaches it and it loses too much heat. In microgravity this happens at very low airflow. |
| **Blowoff extinction** | A flame going out because the airflow is too fast and pushes it off the material. |
| **Flammability boundary (flammability limit)** | The line, on a chart of oxygen against airflow, that separates conditions where a material keeps burning from conditions where it goes out. |
| **U-shaped boundary** | The shape of the flammability boundary in microgravity when airflow is on a log scale: flames go out at both low flow (quenching) and high flow (blowoff), and survive at the lowest oxygen level at a gentle "Goldilocks" airflow in between. |
| **Stretch rate** | A measure of how quickly the flow around a flame stretches it, in 1/s. NASA uses it for rod-shaped samples. Higher airflow means a higher stretch rate. |
| **Limiting oxygen index (LOI)** | The lowest oxygen concentration at which a material or fuel can keep burning under given conditions. |
| **Cool flame** | A low-temperature, nearly invisible flame that some liquid fuels can sustain. Discovered in microgravity by NASA's FLEX experiment. |
| **Exploration atmosphere** | A reduced-pressure, oxygen-enriched cabin atmosphere planned for landers and habitats, for example 8.2 psia with 34% oxygen or 10.2 psia with 26.5% oxygen. ISS uses about 14.7 psia with 21% oxygen. |
| **NASA-STD-6001 Test 1** | NASA's standard upward-flammability test for spacecraft materials, run in normal Earth gravity. |

## Materials

| Term | Meaning |
|---|---|
| **SIBAL fabric** | A cotton-fiberglass composite fabric (75% cotton, 25% fiberglass by mass) used in many NASA fire experiments. It burns like cotton but keeps its shape. The name comes from the "Solid Inflammability Boundary at Low Speed" experiment. |
| **PMMA** | Polymethyl methacrylate, also called acrylic or Plexiglas. A well-studied plastic used as a reference fuel. Tested as thin films, slabs and rods. |
| **Nomex** | A flame-resistant aramid fabric used in flight suits and cargo bags. |
| **Silicone** | A rubber-like polymer used in seals and insulation. |
| **Ultem** | A brand of polyetherimide, a high-temperature plastic. |

## NASA experiments, places and archives

| Term | Meaning |
|---|---|
| **ISS** | International Space Station. |
| **MSG** | Microgravity Science Glovebox, a sealed work area on the ISS where BASS ran. |
| **Cygnus** | An uncrewed cargo spacecraft. The Saffire experiments burned large samples inside Cygnus after it left the ISS, so no crew was at risk. |
| **BASS / BASS-II** | Burning and Suppression of Solids. ISS experiments (about 2012 to 2014) that burned small solid samples in a small wind tunnel at controlled airflow (up to about 40 cm/s) and, in BASS-II, reduced oxygen. |
| **Saffire** | Spacecraft Fire Safety Experiment series (I to VI). Large-scale fires on uncrewed Cygnus vehicles. |
| **SoFIE** | Solid Fuel Ignition and Extinction. An ISS facility studying how solid materials ignite and go out. |
| **FLEX / FLEX-2** | Flame Extinguishment Experiments with burning liquid fuel droplets on the ISS. |
| **ACME** | Advanced Combustion via Microgravity Experiments, studying gas flames. |
| **PSI** | NASA Physical Sciences Informatics, the archive of physical-science experiment data from the ISS and other platforms. Investigations are numbered `PSI-n`. |
| **NTRS** | NASA Technical Reports Server, NASA's public library of papers and reports. Items have numeric IDs such as `20210011385`. |
| **DOI** | Digital Object Identifier, a permanent link to a dataset or paper. |
| **CC0** | A license that places data in the public domain. PSI data uses CC0-1.0. |

## FlameAtlas terms

| Term | Meaning |
|---|---|
| **Test record** | One observed outcome (burned, self-extinguished, no ignition) for one material at one set of conditions. One dot on the map. |
| **Evidence card** | A short structured summary of one NASA source: experiment, material, conditions, outcome, key finding and safety takeaway. |
| **Locator** | Where in the source a value can be found: page plus table, figure or row. |
| **Verified** | A record a team member has checked against its source. Only verified records appear on the map. |
| **Tested envelope** | The region of the map close to real NASA tests. Outside it, FlameAtlas says `UNTESTED`. |
| **Habitat status** | The label for the conditions set with the sliders: `DANGER`, `MARGINAL`, `SELF-EXTINGUISHES`, `UNTESTED` or `NOT ENOUGH DATA`. |
| **Confidence level** | `HIGH`, `MEDIUM` or `LOW`, computed from how many verified tests match a question and how close they are. |
| **Research gap** | A combination of material and conditions that NASA has not tested, shown with a ⚑ flag. |

## AI and software terms

| Term | Meaning |
|---|---|
| **LLM (large language model)** | An AI model that reads and writes text. FlameAtlas uses Anthropic's Claude. |
| **RAG (retrieval-augmented generation)** | First find relevant passages in a fixed set of documents, then have the model write an answer using only those passages. |
| **Embedding** | A list of numbers that represents the meaning of a piece of text, so similar texts can be found quickly. |
| **Vector store** | A database that finds texts with similar embeddings. FlameAtlas uses ChromaDB. |
| **Chunk (passage)** | A short piece of a document, at most about 1,200 characters from one page, stored in the vector store. |
| **Citation** | A link from a sentence in an answer to the exact quoted passage that supports it. |
| **Structured output** | Making the model return data that fits a fixed schema (like a form) instead of free text. |
| **Batch API** | Sending many model requests at once to be processed within hours, at half the price. |
| **Hallucination** | A model stating something that is not supported by its sources. FlameAtlas guards against it with citations and gap flags. |
| **Prompt injection** | Text that tries to trick a model into ignoring its instructions. |
| **Logistic regression** | A simple statistical model that turns inputs (here oxygen and airflow) into a probability between 0 and 1 (here, the chance of burning). |
| **Streamlit** | A Python library for building web apps. |
| **Plotly** | A Python library for interactive charts. |
| **MCP (Model Context Protocol)** | A standard way for AI assistants to call external tools and data. Not used in the hackathon version. |
